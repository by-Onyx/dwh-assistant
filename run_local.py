"""Own a local server while running the existing chat/evaluation CLI."""
import argparse
from pathlib import Path
import subprocess
import sys
from dwh_agent.paths import ROOT
from dwh_agent.local_server import LocalServer

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["local-4b", "local-3b", "local-1.5b"], default="local-4b")
    group=p.add_mutually_exclusive_group()
    group.add_argument("--evaluate", action="store_true")
    group.add_argument("--evaluate-general", action="store_true")
    queries=p.add_mutually_exclusive_group()
    queries.add_argument("--ask")
    queries.add_argument("--request-file")
    p.add_argument("--cpu", action="store_true")
    p.add_argument("--mode", choices=["general", "practicum"], default="general")
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--assets-dir", type=Path, help="Каталог с models/ и runtime/, если они уже скачаны")
    args = p.parse_args()
    script = "evaluate_general.py" if args.evaluate_general else "evaluate.py" if args.evaluate else "assistant.py"
    command = [sys.executable, str(ROOT / script), "--backend", args.backend]
    if not args.evaluate and not args.evaluate_general:
        command += ["--mode", args.mode]
        if args.max_tokens:
            command += ["--max-tokens", str(args.max_tokens)]
        if args.ask:
            command += ["--ask", args.ask]
        if args.request_file:
            command += ["--request-file", args.request_file]
    elif args.ask or args.request_file:
        p.error("Запрос нельзя объединять с оценкой сценариев")
    try:
        with LocalServer(args.backend, assets_dir=args.assets_dir, cpu=args.cpu):
            return subprocess.call(command)
    except (OSError, RuntimeError) as exc:
        p.error(str(exc))

if __name__ == "__main__":
    raise SystemExit(main())
