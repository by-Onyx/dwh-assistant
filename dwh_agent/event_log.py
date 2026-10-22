"""Append-only diagnostic log, separate from long-term fact memory."""
import json
from datetime import datetime, timezone

class EventLog:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
    def write(self, event, **data):
        with self.path.open("a", encoding="utf-8") as out:
            out.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **data}, ensure_ascii=False) + "\n")

