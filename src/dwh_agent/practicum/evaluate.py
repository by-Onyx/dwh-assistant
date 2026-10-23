"""Ten fixed scenarios; two prompt variants; JSONL logs and honest proxies."""
from dwh_agent.paths import LOG_DIR, PRACTICUM_PROMPTS, LAB1_DIR
import argparse
import json
from datetime import datetime
from pathlib import Path
import time
from .assistant import Agent, Client, EventLog, ROOT

CASES = [
    {"id": "orders", "question": "Покажи поля учебной таблицы orders.", "tool": "catalog", "argument": {"table": "orders"}, "terms": [["order_id"], ["customer_id"], ["order_date"], ["status"]]},
    {"id": "items", "question": "Какие поля и ключ у учебной order_items?", "tool": "catalog", "argument": {"table": "order_items"}, "terms": [["order_id"], ["line_no"], ["quantity"], ["unit_price"]]},
    {"id": "missing", "question": "Вызови catalog для таблицы payments и сообщи, есть ли она в учебном каталоге.", "tool": "catalog", "argument": {"table": "payments"}, "terms": [["нет", "отсутств", "не найден", "не существует"]]},
    {"id": "scd2", "question": "Используй памятку scd2: как хранить историю сегмента клиента и выбирать версию на дату продажи?", "tool": "rules", "argument": {"topic": "scd2"}, "terms": [["valid_from"], ["valid_to"], ["дат", "врем"]]},
    {"id": "layers", "question": "Используй памятку layers и предложи слои DWH.", "tool": "rules", "argument": {"topic": "layers"}, "terms": [["raw"], ["staging"], ["core"], ["marts"]]},
    {"id": "quality", "question": "Используй памятку quality: какие проверки качества нужны для загрузки продаж?", "tool": "rules", "argument": {"topic": "quality"}, "terms": [["уник", "дублик"], ["quantity"], ["unit_price"]]},
    {"id": "invalid", "question": 'Проверь макет: grain="", facts=[], dimensions=["customer"].', "tool": "check_design", "argument": {"design": {"grain": "", "facts": [], "dimensions": ["customer"]}}, "terms": [["грануляр"], ["факт"], ["не", "ошиб"]]},
    {"id": "valid", "question": 'Проверь структуру макета: grain="позиция заказа", facts=["quantity","revenue"], dimensions=["customer","product","date"]. Не заявляй, что проверил SQL или БД.', "tool": "check_design", "argument": {"design": {"grain": "позиция заказа", "facts": ["quantity", "revenue"], "dimensions": ["customer", "product", "date"]}}, "terms": [["структур", "макет"], ["прош", "коррект", "валид", "ошибок нет"]]},
    {"id": "mart", "question": "Используя весь учебный каталог, спроектируй витрину продаж по товарам и клиентам. Укажи grain и формулу выручки.", "tool": "catalog", "argument": {"table": "all"}, "terms": [["позиц"], ["quantity"], ["unit_price"], ["клиент", "customer"], ["товар", "product"]]},
    {"id": "clarify", "question": "Спроектируй DWH. Источники, цели и требования пока неизвестны; сначала задай вопросы.", "tool": None, "argument": None, "terms": [["источник"], ["цел", "задач"], ["грануляр", "строк", "детал"]]},
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["local-4b", "local-3b", "local-1.5b", "openrouter"], default="local-3b")
    p.add_argument("--model")
    p.add_argument("--prompt", choices=["baseline", "improved", "both"], default="both")
    args = p.parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    client = Client(args.backend, args.model, max_tokens=650)
    all_rows = []
    for variant in (("baseline", "improved") if args.prompt == "both" else (args.prompt,)):
        path = LOG_DIR / f"eval_{args.backend}_{variant}_{stamp}.log"
        log = EventLog(path)
        log.write("run_config", backend=args.backend, model=client.model, prompt=variant, temperature=client.temperature, max_tokens=client.max_tokens, seed=42, cases=len(CASES), system_prompt=Agent(client, variant).prompt, fewshot=json.loads((PRACTICUM_PROMPTS / "fewshot.json").read_text(encoding="utf-8")) if variant == "improved" else [])
        for case in CASES:
            log.write("case_start", id=case["id"], question=case["question"])
            began = time.monotonic()
            row = {"id": case["id"], "backend": args.backend, "prompt": variant, "log": str(path.relative_to(ROOT))}
            try:
                result = Agent(client, variant, log).ask(case["question"])
                calls = result["calls"]
                tool_ok = any(c["name"] == case["tool"] and c["arguments"] == case["argument"] for c in calls) if case["tool"] else not calls
                answer = result["answer"].lower()
                hits = [any(term in answer for term in group) for group in case["terms"]]
                row.update(completed=True, tool_ok=tool_ok, keyword_ok=all(hits), keyword_hits=hits, repairs=result["repairs"], answer=result["answer"])
            except Exception as exc:
                row.update(completed=False, tool_ok=False, keyword_ok=False, error=str(exc))
            row["seconds"] = round(time.monotonic()-began, 2)
            log.write("case_result", **row)
            all_rows.append(row)
            print(f'{args.backend} {variant} {case["id"]}: completed={row["completed"]} tool={row["tool_ok"]} keywords={row["keyword_ok"]}', flush=True)
    target = LOG_DIR / f"summary_{args.backend}_{stamp}.json"
    target.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Summary:", target)
    return 0 if all(r["completed"] for r in all_rows if r["prompt"] == "improved") else 1

if __name__ == "__main__":
    raise SystemExit(main())
