"""Lifecycle of a server owned by this process, reusable by CLI and Notebook."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlparse
from urllib.request import urlopen
from .paths import BACKENDS_CONFIG, DEFAULT_ASSETS_DIR, LOG_DIR

LOCAL_MODELS = {
    "local-1.5b": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    "local-3b": "qwen2.5-3b-instruct-q4_k_m.gguf",
    "local-4b": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
}

class LocalServer:
    def __init__(self, backend="local-4b", *, assets_dir=None, cpu=False, timeout=120):
        if backend not in LOCAL_MODELS:
            raise ValueError("Нужен локальный профиль: " + ", ".join(LOCAL_MODELS))
        self.backend, self.cpu, self.timeout = backend, cpu, timeout
        self.assets_dir = Path(assets_dir or os.getenv("DWH_ASSETS_DIR") or DEFAULT_ASSETS_DIR).resolve()
        self.config = json.loads(BACKENDS_CONFIG.read_text(encoding="utf-8"))[backend]
        address = urlparse(self.config["base_url"])
        if address.hostname != "127.0.0.1":
            raise ValueError("Локальный сервер должен слушать 127.0.0.1")
        self.port = address.port
        self.process = None
        self._log = None
        self.log_path = LOG_DIR / f"server_{backend}.log"

    def start(self):
        if self.process is not None and self.process.poll() is None:
            return self
        self.close()
        exe = self.assets_dir / "runtime/llama/llama-server.exe"
        model = self.assets_dir / "models" / LOCAL_MODELS[self.backend]
        if not exe.is_file() or not model.is_file():
            raise FileNotFoundError("Запустите scripts/setup_models.ps1 или задайте assets_dir с models/ и runtime/.")
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", self.port)) == 0:
                raise RuntimeError(f"Порт {self.port} занят. Завершите прежний сервер или подключитесь к нему без автозапуска.")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("w", encoding="utf-8")
        try:
            self.process = subprocess.Popen([
                str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
                "-c", "8192", "-np", "1", "-ngl", "0" if self.cpu else "99",
                "--alias", self.config["model"],
            ], stdout=self._log, stderr=subprocess.STDOUT,
               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(f"llama-server завершился; см. {self.log_path}; попробуйте CPU.")
                try:
                    with urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1):
                        return self
                except OSError:
                    time.sleep(0.25)
            raise RuntimeError("Истекло время ожидания llama-server")
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process = None
        if self._log is not None:
            self._log.close()
            self._log = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()
