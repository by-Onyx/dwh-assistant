"""Repository resources are anchored to the installed editable package, never cwd."""
import os
from pathlib import Path


def find_project_root():
    configured = os.getenv("DWH_PROJECT_ROOT")
    candidates = [Path(configured).expanduser().resolve()] if configured else list(Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file() and (candidate / "configs/backends.json").is_file():
            return candidate
    raise RuntimeError("Не найден репозиторий DWH. Установите его через pip install -e . или задайте DWH_PROJECT_ROOT.")


ROOT = find_project_root()
CONFIG_DIR = ROOT / "configs"
BACKENDS_CONFIG = CONFIG_DIR / "backends.json"
MODEL_MANIFEST = CONFIG_DIR / "model_manifest.json"
LAB1_DIR = ROOT / "labs/01_dwh_agent"
LAB2_DIR = ROOT / "labs/02_fact_memory"
PRACTICUM_PROMPTS = LAB1_DIR / "prompts"
FACT_PROMPTS = LAB2_DIR / "prompts"
VAR_DIR = ROOT / "var"
LOG_DIR = VAR_DIR / "logs"
MEMORY_FILE = VAR_DIR / "memory.json"
DEFAULT_ASSETS_DIR = VAR_DIR
