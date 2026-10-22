"""Real local LLM + two independent Python processes + fact-file verification."""
import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from dwh_agent.fact_memory import FileFactMemory
from dwh_agent.local_server import LocalServer
from dwh_agent.paths import ROOT

INTRO = "Меня зовут Алексей. Мой стек — Python и PostgreSQL. Мой уровень — начинающий аналитик. Моя цель — спроектировать DWH для автосалона. Предметная область — автосалон."
RECALL = "Как меня зовут, какой у меня стек и какая цель? Затем задай следующий вопрос анкеты."
DEMO_USER = "restart_demo"


def run_restart_demo(memory_path, *, backend="local-4b", assets_dir=None, start_server=True, cpu=False):
    memory_path = Path(memory_path).resolve()
    # This function is explicitly a resettable demo. Never use the live user memory.
    if memory_path == (ROOT / "memory.json").resolve():
        raise ValueError("Демонстрация не может сбрасывать рабочий memory.json")
    FileFactMemory(memory_path, DEMO_USER).forget()
    records = []
    context = LocalServer(backend, assets_dir=assets_dir, cpu=cpu) if start_server else nullcontext()
    with context:
        for message in (INTRO, RECALL):
            completed = subprocess.run([
                sys.executable, str(ROOT / "memory_session.py"), "--backend", backend,
                "--memory", str(memory_path), "--user-id", DEMO_USER, "--message", message,
            ], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=240,
               env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            if completed.returncode:
                raise RuntimeError("Процесс демонстрации завершился с ошибкой: " + completed.stderr[-1500:])
            records.append(json.loads(completed.stdout))
    first, second = records
    expected = {"name": "Алексей", "stack": "Python и PostgreSQL", "level": "начинающий аналитик",
                "goals": "спроектировать DWH для автосалона", "domain": "автосалон"}
    checks = {
        "different_processes": first["pid"] != second["pid"],
        "first_started_empty": first["facts_before"] == {},
        "facts_extracted": all(first["facts"].get(key) == value for key, value in expected.items()),
        "loaded_from_file": first["facts"] == second["facts_before"],
        "question_did_not_change_facts": second["facts"] == second["facts_before"],
        "recall_mentions_facts": all(term in second["answer"].casefold() for term in ["алексей", "python", "postgresql", "автосалон"]),
        "extraction_succeeded": all(record["extraction_ok"] for record in records),
    }
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "backend": backend,
            "langchain_core": importlib.metadata.version("langchain-core"),
            "checks": checks, "passed": all(checks.values()), "sessions": records,
            "memory": json.loads(memory_path.read_text(encoding="utf-8"))}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="local-4b")
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    evidence = run_restart_demo(ROOT / "examples/memory.json", backend=args.backend,
                                assets_dir=args.assets_dir, cpu=args.cpu)
    destination = ROOT / "evidence/memory_restart.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "checks": evidence["checks"],
                      "answers": [row["answer"] for row in evidence["sessions"]]}, ensure_ascii=False, indent=2))
    return 0 if evidence["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
