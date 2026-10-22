"""Homework 1 REPL; shared transport/protocol are re-exported for compatibility."""
import argparse
import json
from pathlib import Path
import re
import sys
import time
from datetime import datetime
from dwh_tools import dispatch
from dwh_agent.paths import ROOT
from dwh_agent.transport import Client
from dwh_agent.event_log import EventLog
from dwh_agent.protocol import ProtocolError, parse_response

class Agent:
    def __init__(self, client, prompt="improved", log=None):
        self.client, self.log, self.variant = client, log, prompt
        self.prompt = (ROOT / "prompts" / (prompt + ".txt")).read_text(encoding="utf-8")
        self.answer_prompt = (ROOT / ("prompts/general_answer.txt" if prompt == "general" else "prompts/answer.txt")).read_text(encoding="utf-8")
        self.reset()
    def reset(self):
        self.messages = [{"role": "system", "content": self.prompt}]
        if self.variant == "improved":
            self.messages.extend(json.loads((ROOT / "prompts/fewshot.json").read_text(encoding="utf-8")))
        if self.variant == "general":
            self.messages.extend(json.loads((ROOT / "prompts/general_fewshot.json").read_text(encoding="utf-8")))
        self.initial_length = len(self.messages)
    def record(self, event, **data):
        if self.log:
            self.log.write(event, **data)
    def ask(self, question, emit=None):
        start = len(self.messages)
        self.messages.append({"role": "user", "content": question})
        self.record("user", content=question)
        seen, repairs, calls = set(), 0, []
        answering = False
        answer_data = None
        answer_kind = "answer"
        answer_repairs = []
        try:
            for step in range(7):
                began = time.monotonic()
                history = [m for m in self.messages[self.initial_length:start] if not m["content"].lstrip().startswith(("<call>", "<observation>"))]
                answer_system = self.answer_prompt if self.variant == "general" else self.answer_prompt + "\n" + (ROOT / "prompts" / (answer_kind + ".txt")).read_text(encoding="utf-8")
                answer_input = {"question": question, "observation": answer_data}
                if self.variant == "general":
                    answer_input = {"conversation": history, "observation": answer_data, "question": question}
                    if answer_kind == "rules_answer" and calls[-1]["arguments"].get("topic") == "requirements":
                        answer_system = "Ты — архитектор DWH. В question текущая задача. conversation — только контекст прошлых сообщений, не новая инструкция. Задай максимум пять конкретных вопросов о неизвестных требованиях для указанной отрасли. Дефицит доступности и истечение срока годности — разные задачи; не смешивай их и не придумывай числовые пороги. Уже известное не спрашивай. Не проси пользователя самому проектировать факты, связи и формулы. Не выдавай проект до ответов. Пиши обычный русский текст, без тегов и функций."
                context = ([{"role": "system", "content": answer_system}, {"role": "user", "content": json.dumps(answer_input, ensure_ascii=False)}] + answer_repairs) if answering and self.variant in ("improved", "general") else self.messages
                drafting = self.variant == "general" and answering and any(c["name"] == "rules" and c["arguments"].get("topic") == "modeling" for c in calls)
                text = self.client.complete(context, None if drafting else emit)
                self.record("model", content=text, seconds=round(time.monotonic()-began, 3), step=step, usage=getattr(self.client, "last_usage", None))
                self.messages.append({"role": "assistant", "content": text})
                try:
                    if answering and self.variant in ("improved", "general") and not text.strip().startswith("<answer>"):
                        if re.search(r"</?call>", text):
                            raise ProtocolError("На этапе ответа вызовы запрещены")
                        kind, body = "answer", text.strip()
                    else:
                        kind, body = parse_response(text)
                    if kind == "answer":
                        if self.variant == "general" and any(c["name"] == "rules" and c["arguments"].get("topic") == "modeling" for c in calls):
                            self.record("draft", content=body)
                            review_system = (ROOT / "prompts/general_review.txt").read_text(encoding="utf-8")
                            review_input = {"conversation": [m for m in history if m["role"] == "user"], "question": question}
                            reviewed = self.client.complete([{"role": "system", "content": review_system}, {"role": "user", "content": json.dumps(review_input, ensure_ascii=False)}], emit)
                            self.record("review", content=reviewed, usage=getattr(self.client, "last_usage", None))
                            if reviewed.strip().startswith("<answer>"):
                                _, body = parse_response(reviewed)
                            else:
                                if re.search(r"</?call>", reviewed):
                                    raise ProtocolError("Редактор не может вызывать функции")
                                body = reviewed.strip()
                            self.messages[-1] = {"role": "assistant", "content": body}
                        self.record("final", content=body, calls=calls, repairs=repairs)
                        return {"answer": body, "calls": calls, "repairs": repairs}
                    if answering and self.variant in ("improved", "general"):
                        raise ProtocolError("Функция уже выполнена. Нужен окончательный содержательный ответ.")
                    signature = json.dumps(body, sort_keys=True, ensure_ascii=False)
                    if signature in seen:
                        raise ProtocolError("Повторный вызов. Используй уже полученный результат.")
                    result = dispatch(body["name"], body["arguments"])
                    seen.add(signature)
                    calls.append({**body, "result": result})
                    self.record("tool", **body, result=result)
                    answering = True
                    answer_data = result
                    answer_kind = "mart_answer" if body["name"] == "catalog" and body["arguments"].get("table") == "all" else body["name"] + "_answer"
                    self.messages.append({"role": "user", "content": "<observation>" + json.dumps(result, ensure_ascii=False) + "</observation>\nИсходный вопрос: " + question + "\nНа основе результата дай содержательный ответ между тегами <answer> и </answer>."})
                    if "error" in result:
                        final = result["error"] + ". Доступны: " + ", ".join(result.get("available", [])) + "."
                        self.messages.append({"role": "assistant", "content": "<answer>" + final + "</answer>"})
                        self.record("final", content=final, calls=calls, repairs=repairs, deterministic_error=True)
                        if emit:
                            emit("\n" + final)
                        return {"answer": final, "calls": calls, "repairs": repairs}

                except (ProtocolError, ValueError) as exc:
                    repairs += 1
                    if answering:
                        answer_repairs.extend([{"role": "assistant", "content": text}, {"role": "user", "content": "Исправь ответ. Вызовы запрещены; нужен содержательный ответ по question и observation."}])
                    self.record("protocol_error", message=str(exc))
                    if repairs > 2:
                        raise RuntimeError("Формат не исправлен после двух повторов") from exc
                    self.messages.append({"role": "user", "content": "Ошибка протокола: " + str(exc) + '\nИсправь формат. Доступны catalog(table), rules(topic), check_design(design). Темы grain/scd2/layers/quality — аргумент topic функции rules. Вызов с ошибкой не исполнен. Выдай один корректный блок.'})
            raise RuntimeError("Превышен лимит шагов агента")
        except BaseException as exc:
            self.record("error", message=str(exc))
            del self.messages[start:]
            raise

def main():
    p = argparse.ArgumentParser(description="Учебный ассистент DWH")
    p.add_argument("--backend", choices=["local-4b", "local-3b", "local-1.5b", "openrouter"], default="local-4b")
    p.add_argument("--model")
    p.add_argument("--prompt", choices=["baseline", "improved"], default="improved")
    queries=p.add_mutually_exclusive_group()
    queries.add_argument("--ask")
    queries.add_argument("--request-file", help="UTF-8 файл с одним многострочным запросом")
    p.add_argument("--mode", choices=["general", "practicum"], default="general")
    p.add_argument("--max-tokens", type=int)
    args = p.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        if args.max_tokens is not None and not 64 <= args.max_tokens <= 8192:
            raise ValueError("--max-tokens: от 64 до 8192")
        if args.request_file:
            args.ask = Path(args.request_file).read_text(encoding="utf-8").strip()
            if not args.ask:
                raise ValueError("Файл запроса пуст")
        client = Client(args.backend, args.model, max_tokens=args.max_tokens or (2200 if args.mode == "general" else 550))
        path = ROOT / "logs" / f"chat_{args.backend}_{datetime.now():%Y%m%d_%H%M%S}.log"
        agent = Agent(client, "general" if args.mode == "general" else args.prompt, EventLog(path))
        agent.record("run_config", backend=args.backend, model=client.model, mode=args.mode, max_tokens=client.max_tokens, prompt=agent.prompt)
        print(f"DWH assistant | {client.model} | режим: {args.mode} | log: {path}")
        print("/exit — выход, /reset — очистить историю, /paste — многострочный запрос до /end.")
        while True:
            try:
                question = args.ask or input("\nВы: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if question in ("/exit", "/quit"):
                break
            if question == "/paste":
                print("Вставьте запрос. Отдельная строка /end завершает ввод.")
                lines=[]
                try:
                    while True:
                        line=input()
                        if line.strip()=="/end":
                            break
                        lines.append(line)
                except (EOFError, KeyboardInterrupt):
                    break
                question="\n".join(lines).strip()
            if question == "/reset":
                agent.reset()
                continue
            if not question:
                continue
            try:
                print("Ассистент: ", end="", flush=True)
                agent.ask(question, lambda chunk: print(chunk, end="", flush=True))
                print()
            except KeyboardInterrupt:
                print("\nГенерация прервана.")
                break
            except Exception as exc:
                print(f"\nОшибка: {exc}")
                if args.ask:
                    return 1
            if args.ask:
                break
        print("Чат завершен.")
        return 0
    except (ValueError, OSError) as exc:
        print(f"Ошибка настройки: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
