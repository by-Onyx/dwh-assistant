"""Strict text protocol used by homework 1."""
import json
import re

class ProtocolError(ValueError):
    pass

def parse_response(text):
    if len(text) > 30000:
        raise ProtocolError("Ответ слишком длинный")
    m = re.fullmatch(r"\s*<(call|answer)>([\s\S]*?)</\1>\s*", text)
    if not m:
        raise ProtocolError("Нужен один блок <call>JSON</call> или <answer>текст</answer>")
    kind, body = m.groups()
    if kind == "answer":
        if not body.strip() or re.search(r"</?(?:call|answer)>", body):
            raise ProtocolError("Пустой ответ или вложенный блок")
        return kind, body.strip()
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ProtocolError("Повторяющийся JSON-ключ")
            result[k] = v
        return result
    def bad_constant(x):
        raise ProtocolError("Недопустимое число")
    try:
        call = json.loads(body, object_pairs_hook=unique, parse_constant=bad_constant)
    except (ValueError, RecursionError) as exc:
        raise ProtocolError(f"Некорректный JSON: {exc}") from exc
    if not isinstance(call, dict) or set(call) != {"name", "arguments"} or not isinstance(call["name"], str) or not isinstance(call["arguments"], dict):
        raise ProtocolError("JSON: только name (строка) и arguments (объект)")
    return kind, call

