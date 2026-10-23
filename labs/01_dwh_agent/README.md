# Лабораторная 01 — ассистент по проектированию DWH

[← Оглавление](../../README.md)

Консольный агент для разных отраслей. История диалога хранится в текущем сеансе; модель выводит обычный текст с блоками `<call>JSON</call>`, приложение проверяет JSON и исполняет разрешенную функцию. Нативные tools/function calling и MCP не используются.

**Пример работы находится здесь: [запрос и фактический ответ про автосалон](examples/car_dealership.md).** Ответ сохранён без ручных исправлений, включая ошибки модели.

## Запуск

Сначала выполните установку из [корневого README](../../README.md). Команды ниже — из корня репозитория:

```powershell
.\.venv\Scripts\python.exe labs/01_dwh_agent/run_local.py --backend local-4b
.\.venv\Scripts\python.exe labs/01_dwh_agent/run_local.py --backend local-3b --mode practicum
.\.venv\Scripts\python.exe labs/01_dwh_agent/run_local.py --backend local-1.5b
```

По умолчанию общий режим `general`, Qwen3-4B-Instruct-2507 Q4_K_M. `practicum` использует первоначальные промпты задания. В случае проблем с Vulkan добавьте `--cpu`. Launcher запускает свой сервер на 127.0.0.1 и завершает его после чата. Порты: 4B — 8082, 3B — 8080, 1.5B — 8081; профили — [configs/backends.json](../../configs/backends.json).

Команды чата: `/paste` — многострочный запрос до отдельной строки `/end`; `/reset` — новая история; `/exit` — выход. Ctrl+C и EOF завершают чат. Контекст сервера — 8192 токена. История из журналов автоматически не восстанавливается.

Запрос из файла:

```powershell
.\.venv\Scripts\python.exe labs/01_dwh_agent/run_local.py --request-file labs/01_dwh_agent/examples/car_dealership.txt
```

Также есть [запрос для аптеки](examples/pharmacy.txt) и [продолжение с допущениями](examples/pharmacy_followup.txt). Названия проектных таблиц являются предложениями, а не обнаруженной схемой реальной БД.

## OpenRouter

```powershell
$env:OPENROUTER_API_KEY = 'ваш-ключ'
.\.venv\Scripts\python.exe labs/01_dwh_agent/assistant.py --backend openrouter
```

Ключ читается из окружения. Текущий профиль — liquid/lfm-2.5-2.6b:free; его работоспособность действующим ключом не подтверждена. Исторические облачные результаты относятся к другому профилю. При смене модели соблюдайте ограничение до 4B. Доступность и стоимость определяет провайдер.

## Проверка и материалы

```powershell
.\.venv\Scripts\python.exe labs/01_dwh_agent/run_local.py --backend local-1.5b --evaluate
.\.venv\Scripts\python.exe labs/01_dwh_agent/run_local.py --backend local-3b --evaluate
.\.venv\Scripts\python.exe labs/01_dwh_agent/run_local.py --backend local-4b --evaluate-general
```

- [Первоначальный отчет](reports/homework.md): baseline/improved двух локальных моделей и исторический OpenRouter.
- [Общий режим: реальные результаты и ошибки](reports/general_mode.md).
- [Пример аптеки после ручной проверки](reports/pharmacy_reviewed.md).
- [Сохранённые журналы и сводки](evidence/logs/).
- [Промпты](prompts/).
- [Исходники](../../src/dwh_agent/practicum/).

Три функции: `catalog(table)` — учебный каталог, `rules(topic)` — памятки, `check_design(design)` — структурная проверка. Приложение не выполняет SQL. Проекты требуют проверки: правильный выбор функции не означает правильный DWH-проект.

Файлы Python в этой папке — короткие точки запуска. Логика находится в общем пакете; ее не нужно копировать для следующей лабораторной.
