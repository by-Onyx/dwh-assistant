"""Own one llama.cpp process; health check; chat/evaluate; stop."""
import argparse
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent

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
    args = p.parse_args()
    profiles={"local-3b": ("qwen2.5-3b-instruct-q4_k_m.gguf",8080,"qwen2.5-3b"), "local-1.5b": ("qwen2.5-1.5b-instruct-q4_k_m.gguf",8081,"qwen2.5-1.5b"), "local-4b": ("Qwen3-4B-Instruct-2507-Q4_K_M.gguf",8082,"qwen3-4b")}
    filename,port,alias=profiles[args.backend]
    exe = ROOT / "runtime/llama/llama-server.exe"
    model = ROOT / "models" / filename
    if not exe.exists() or not model.exists():
        p.error("Сначала запустите setup.ps1")
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
            p.error(f"Порт {port} занят; завершите сервер или вызовите assistant.py напрямую")
    except OSError:
        pass
    (ROOT / "logs").mkdir(exist_ok=True)
    with (ROOT / f"logs/server_{args.backend}.log").open("w", encoding="utf-8") as out:
        proc = subprocess.Popen([str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(port), "-c", "8192", "-np", "1", "-ngl", "0" if args.cpu else "99", "--alias", alias], stdout=out, stderr=subprocess.STDOUT)
        try:
            ready = False
            for _ in range(120):
                if proc.poll() is not None:
                    raise RuntimeError("llama-server завершился; смотрите log, попробуйте --cpu")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                        ready = True
                        break
                except OSError:
                    time.sleep(1)
            if not ready:
                raise RuntimeError("Сервер не готов за 120 секунд")
            command = [sys.executable, str(ROOT / ("evaluate_general.py" if args.evaluate_general else "evaluate.py" if args.evaluate else "assistant.py")), "--backend", args.backend]
            if not args.evaluate and not args.evaluate_general:
                command += ["--mode", args.mode]
                if args.max_tokens:
                    command += ["--max-tokens", str(args.max_tokens)]
            if args.ask:
                command += ["--ask", args.ask]
            if args.request_file:
                command += ["--request-file", args.request_file]
            return subprocess.call(command)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

if __name__ == "__main__":
    raise SystemExit(main())
