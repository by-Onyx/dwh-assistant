"""Atomic, profile-scoped fact storage. No conversation messages are persisted."""
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Literal
from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field

FactKey = Literal["name", "stack", "level", "goals", "domain", "sources", "refresh_schedule"]
FACT_KEYS = ("name", "stack", "level", "goals", "domain", "sources", "refresh_schedule")
QUESTIONS = {
    "name": "Как к вам обращаться?",
    "stack": "С каким стеком данных вы работаете?",
    "level": "Каков ваш опыт в проектировании DWH?",
    "goals": "Какую задачу вы хотите решить с помощью DWH?",
    "domain": "Для какой предметной области проектируем хранилище?",
    "sources": "Какие источники данных доступны?",
    "refresh_schedule": "Как часто нужно обновлять данные?",
}

class MemoryFormatError(ValueError):
    """Invalid existing memory is never silently replaced."""

class FactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: FactKey
    value: str = Field(min_length=1, max_length=500)
    evidence: str = Field(min_length=1, max_length=1000)

class FactPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    updates: list[FactUpdate] = Field(max_length=7)


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Повторяющийся JSON-ключ")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("Недопустимая JSON-константа")
    return json.loads(text, object_pairs_hook=unique, parse_constant=invalid_constant)


def normalized(text):
    return " ".join(text.split()).casefold()


def validate_patch(patch, message):
    """Require literal evidence in THIS user message, not the assistant's output."""
    patch = patch if isinstance(patch, FactPatch) else FactPatch.model_validate(patch)
    seen = set()
    for update in patch.updates:
        if update.key in seen:
            raise ValueError("Поле повторяется в обновлении")
        seen.add(update.key)
        if not update.value.strip() or not update.evidence.strip():
            raise ValueError("Пустое значение факта")
        if normalized(update.evidence) not in normalized(message):
            raise ValueError("Цитата не найдена в текущем сообщении пользователя")
        if normalized(update.value) not in normalized(update.evidence):
            raise ValueError("Значение факта должно быть дословной частью цитаты")
        if re.search(r"(?:sk-[\w-]{12,}|Bearer\s+\S+|ghp_[\w]+)", update.value, re.I):
            raise ValueError("Секрет нельзя сохранять в профиль")
    return patch


class FileFactMemory:
    """Explicit load_memory_variables/save_context interface for an LCEL chain.

    Runnable chains call this adapter directly. We intentionally do not inherit
    deprecated chat-buffer memory classes: this file stores facts, not messages.
    """
    memory_keys = ["facts"]

    def __init__(self, path, user_id="default"):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id):
            raise ValueError("user_id: 1–64 латинских букв, цифр, _ или -")
        self.path = Path(path).resolve()
        self.user_id = user_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.path) + ".lock", timeout=10)
        self.load_memory_variables({})  # validate an existing file immediately

    def _read(self):
        if not self.path.exists():
            return {"version": 1, "profiles": {}}
        try:
            if self.path.stat().st_size > 2_000_000:
                raise ValueError("Файл памяти слишком большой")
            data = strict_json(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) != {"version", "profiles"}:
                raise ValueError("Неверная структура памяти")
            if type(data["version"]) is not int or data["version"] != 1 or not isinstance(data["profiles"], dict):
                raise ValueError("Неподдерживаемая версия памяти")
            for user_id, profile in data["profiles"].items():
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id):
                    raise ValueError("Неверный идентификатор профиля")
                if not isinstance(profile, dict) or set(profile) != {"facts"} or not isinstance(profile["facts"], dict):
                    raise ValueError("В профиле допустим только facts")
                for key, value in profile["facts"].items():
                    if key not in FACT_KEYS or not isinstance(value, str) or not value.strip() or len(value) > 500:
                        raise ValueError("Некорректный факт")
            return data
        except (ValueError, UnicodeError) as exc:
            raise MemoryFormatError(f"Повреждена память {self.path.name}: {exc}. Исходный файл сохранен.") from exc

    def _write(self, data):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=self.path.name + ".", suffix=".tmp", delete=False) as out:
                temp_path = Path(out.name)
                json.dump(data, out, ensure_ascii=False, indent=2)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def load_memory_variables(self, inputs=None):
        with self.lock:
            data = self._read()
            return {"facts": dict(data["profiles"].get(self.user_id, {"facts": {}})["facts"])}

    def save_context(self, inputs, outputs):
        patch = validate_patch(outputs["fact_patch"], inputs["message"])
        with self.lock:
            data = self._read()
            if patch.updates:
                facts = data["profiles"].setdefault(self.user_id, {"facts": {}})["facts"]
                for update in patch.updates:
                    facts[update.key] = update.value.strip()
                self._write(data)
            return dict(data["profiles"].get(self.user_id, {"facts": {}})["facts"])

    def forget(self, key=None):
        if key is not None and key not in FACT_KEYS:
            raise ValueError("Неизвестное поле памяти")
        with self.lock:
            data = self._read()
            profile = data["profiles"].get(self.user_id)
            if profile is not None:
                if key is None:
                    del data["profiles"][self.user_id]
                else:
                    profile["facts"].pop(key, None)
                self._write(data)

    def next_question(self):
        facts = self.load_memory_variables()["facts"]
        return next((QUESTIONS[key] for key in FACT_KEYS if key not in facts), None)
