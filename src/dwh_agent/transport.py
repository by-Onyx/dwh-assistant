"""Shared OpenAI-compatible SSE transport; no LangChain dependency."""
import json
import os
from urllib import request, error
from .paths import BACKENDS_CONFIG

class Client:
    def __init__(self, backend, model=None, max_tokens=550, temperature=0.1, stop=None):
        self.backend = backend
        self.config = json.loads(BACKENDS_CONFIG.read_text(encoding="utf-8"))[backend]
        self.model = (model or os.getenv("OPENROUTER_MODEL", "") or self.config["model"]) if backend == "openrouter" else (model or self.config["model"])
        self.key = os.getenv(self.config.get("key_env", ""), "")
        if backend == "openrouter" and (not self.key or not self.model):
            raise ValueError("Задайте OPENROUTER_API_KEY и OPENROUTER_MODEL (или --model). Ключ не логируется.")
        self.max_tokens, self.temperature = max_tokens, temperature
        self.stop = ["\nObservation:", "\n<answer>", "\nПользователь:", "\nАссистент:"] if stop is None else stop

    def complete(self, messages, emit=None):
        # No native tools/function calling, tool_choice, response_format or MCP.
        payload = {"model": self.model, "messages": messages, "stream": True, "temperature": self.temperature, "max_tokens": self.max_tokens, "seed": 42, "stop": self.stop}
        if self.backend == "openrouter" and self.config.get("reasoning"):
            payload["reasoning"] = self.config["reasoning"]
        self.last_usage = None
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        req = request.Request(self.config["base_url"] + "/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode(), headers=headers)
        chunks, done, finish = [], False, None
        try:
            with request.urlopen(req, timeout=180) as response:
                for raw in response:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        done = True
                        break
                    item = json.loads(data)
                    if item.get("usage") is not None:
                        self.last_usage = item["usage"]
                    if item.get("error"):
                        raise RuntimeError("Ошибка провайдера в потоке")
                    for choice in item.get("choices", []):
                        finish = choice.get("finish_reason") or finish
                        chunk = choice.get("delta", {}).get("content") or ""
                        chunks.append(chunk)
                        if emit and chunk:
                            emit(chunk)
        except error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}: проверьте модель, доступ и параметры") from None
        if not done or finish == "length":
            raise RuntimeError("Поток оборвался или достигнут max_tokens; ответ не принят")
        text = "".join(chunks)
        if not text.strip():
            raise RuntimeError("Пустой ответ модели")
        return text

