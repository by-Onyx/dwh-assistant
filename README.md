# DWH Assistant — лабораторные работы

Учебный проект по AI-агентам: проектирование DWH с локальными моделями **до 4B**. Каждая лабораторная работа содержит свою инструкцию, примеры и результаты; общий код используется из Python-пакета `src/dwh_agent`.

## Лабораторные работы

| Работа | Содержание | Материалы |
|---|---|---|
| [01. DWH-агент](labs/01_dwh_agent/README.md) | Консольный чат, ручной разбор вызовов функций, сравнение промптов | [Пример автосалона: запрос и неизмененный ответ](labs/01_dwh_agent/examples/car_dealership.md) |
| [02. LangChain и память фактов](labs/02_fact_memory/README.md) | Память в JSON, профили, восстановление после перезапуска, отдельная служебная CELL | [Notebook](labs/02_fact_memory/notebooks/02_fact_memory.ipynb) · [Пример памяти](labs/02_fact_memory/examples/memory.json) |

## Быстрый старт

Windows, Python 3.12+. Все команды ниже выполняются **из корня репозитория**.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install -r requirements/notebook.txt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_models.ps1
```

Установка `-e .` связывает общий пакет с исходниками в `src/`; после изменения кода переустановка не нужна. Для работы только с лабораторной 01 зависимости Notebook можно пропустить. Установка моделей скачивает llama.cpp b11524 и Qwen 1.5B, 3B, 4B, проверяет SHA-256. По умолчанию модели находятся в `var/models/`, сервер — в `var/runtime/`.

**Лабораторная 01 — консольный чат:**

```powershell
.\.venv\Scripts\python.exe labs/01_dwh_agent/run_local.py --backend local-4b
```

**Лабораторная 02 — Notebook:**

```powershell
.\.venv\Scripts\python.exe -m ipykernel install --prefix .venv --name dwh-assistant --display-name "Python (DWH assistant)"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_notebook.ps1
```

Выберите ядро **Python (DWH assistant)**. Для уже скачанных моделей задайте каталог, внутри которого лежат `models/` и `runtime/`; повторная загрузка не нужна:

```powershell
$env:DWH_ASSETS_DIR = 'D:\папка-с-моделями-и-runtime'
```

Эту переменную используют обе лабораторные. Для CLI также доступен `--assets-dir`, для скриптов — `-AssetsDir`. Инструкции по CPU, OpenRouter, командам чата и перезапуску находятся в README соответствующей работы.

## Структура

```text
labs/
  01_dwh_agent/        README, запуск, промпты, примеры, отчеты и доказательства работы 01
  02_fact_memory/     README, Notebook, память-пример, промпты и результаты работы 02
src/dwh_agent/        общий Python-пакет и реализация обеих лабораторных
configs/             профили серверов и манифест моделей
scripts/             установка моделей и запуск Notebook
requirements/        зависимости Notebook и проверенный снимок окружения
tests/              автоматические тесты
docs/               описание структуры и перехода со старых путей
var/                 локальные модели, сервер, логи и личная память (вне Git)
pyproject.toml       установка пакета и команды dwh-chat / dwh-memory-demo
README.md            оглавление и быстрый старт
```

[Архитектура и правила размещения файлов](docs/STRUCTURE.md) · [Переход со старой структуры](docs/MIGRATION.md)

## Проверки

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.\.venv\Scripts\python.exe labs/02_fact_memory/verify_memory_restart.py
```

Unit-тесты не требуют сервера модели. Проверка перезапуска использует реальную модель и два независимых процесса. Сохранённые доказательства находятся внутри `labs/*/evidence/`; текущие логи — в `var/logs/`.

Модели, среда Python, личная память и ключи исключены из Git. Все ссылки на материалы относительные и работают при загрузке репозитория целиком.
