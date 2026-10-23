"""One process/one turn, used to demonstrate a real application restart."""
import argparse
import json
import os
import sys
from pathlib import Path
from dwh_agent.fact_agent import FactAgent
from dwh_agent.fact_memory import FileFactMemory


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="local-4b")
    parser.add_argument("--memory", type=Path, required=True)
    parser.add_argument("--user-id", default="default")
    parser.add_argument("--message", required=True)
    args = parser.parse_args()
    events = []
    memory = FileFactMemory(args.memory, args.user_id)
    before = memory.load_memory_variables()["facts"]
    agent = FactAgent(memory, backend=args.backend, on_event=events.append)
    result = agent.ask(args.message)
    print(json.dumps({"pid": os.getpid(), "user_id": args.user_id,
                      "facts_before": before, "message": args.message,
                      **result, "events": events}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
