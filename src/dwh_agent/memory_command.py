"""Explicit memory tool for the lab chat."""
from .fact_memory import FACT_KEYS, FactPatch, FactUpdate


def remember(command, memory):
    """Parse /remember <field> <free text> and persist one validated update."""
    args = command.split(maxsplit=2)
    if len(args) != 3 or args[0] != "/remember" or args[1] not in FACT_KEYS:
        raise ValueError("Формат: /remember <поле> <значение>. Поля: " + ", ".join(FACT_KEYS))
    _, key, value = args
    value = value.strip()
    patch = FactPatch(updates=[FactUpdate(key=key, value=value, evidence=value)])
    facts = memory.save_context({"message": command}, {"fact_patch": patch})
    return key, facts
