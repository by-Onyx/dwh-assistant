"""Fixed educational constants; no database or arbitrary execution."""
from copy import deepcopy

CATALOG = {
    "orders": {"grain": "один заказ", "pk": ["order_id"], "fields": ["order_id", "customer_id", "order_date", "status"], "fk": {"customer_id": "customers.customer_id"}},
    "order_items": {"grain": "одна позиция заказа", "pk": ["order_id", "line_no"], "fields": ["order_id", "line_no", "product_id", "quantity", "unit_price"], "fk": {"order_id": "orders.order_id", "product_id": "products.product_id"}},
    "customers": {"grain": "текущее состояние клиента", "pk": ["customer_id"], "fields": ["customer_id", "customer_name", "segment"], "history": False},
    "products": {"grain": "текущее состояние товара", "pk": ["product_id"], "fields": ["product_id", "product_name", "category"], "history": False},
}
RULES = {
    "grain": "Сначала определи одну строку факта. Заказ и позиция заказа — разные grain. Позиции: ключ order_id + line_no; quantity аддитивно; revenue=quantity*unit_price. Цена за единицу не аддитивна. Разные валюты нельзя складывать без конвертации; валюты в учебном каталоге нет.",
    "scd2": "SCD2: surrogate key версии, business key, valid_from, valid_to, is_current. Интервалы [valid_from,valid_to) не перекрываются. Факт связывается с версией на дату события, а не текущей. Нужен источник изменений/снимков и политика поздних событий. Учебный customers хранит только текущее состояние; историю восстановить нельзя.",
    "layers": "Учебный вариант: raw (исходные загрузки с источником и временем), staging (типизация/дедупликация), core (интеграция/история), marts (бизнес-факты и измерения). Для небольшой задачи слои можно упростить. CDC, расписание, объем и SLA требуют уточнения.",
    "quality": "Проверки: уникальность ключей; not null только для обязательных полей; связи FK; quantity>0; unit_price>=0; сверка числа строк и сумм с источником; отсутствие пересечения SCD2-интервалов; идемпотентная загрузка (повтор того же пакета не создает дубликатов и не меняет итог). Это список проверок, а не результат исполнения.",
}

RULES.update({'requirements': 'Уточни цель/потребителей и решения на основе аналитики; доступные источники/ключи; бизнес-процессы и гранулярность; историзацию/партии/единицы; объем, частоту и SLA. Уже известные ответы не спрашивай повторно. Раздели факты пользователя, проектные предложения и неизвестные требования.', 'modeling': 'От целей выдели бизнес-процессы. Для каждого факта сначала задай одну строку: событие/позиция, движение, периодический снимок или накопительный снимок. Общие согласованные измерения связывают процессы, но факты разных grain напрямую не соединяй без агрегации к общему уровню. Ключи/поля проекта — предложения. Укажи аддитивные/полуаддитивные меры и формулы, историю атрибутов, происхождение данных, поздние изменения и проверки. Для неизвестных источников не применяй учебный каталог как реальную схему.', 'inventory': 'Запасы — периодический снимок: сущность × локация × дата; партия/статус добавляются, если нужны и есть в источнике. Остатки суммируются по совместимым товарам/локациям/партиям, но не по времени. Движения — отдельный факт с типом, количеством и исходной/целевой локацией. Партии и сроки годности требуют ключей и истории поставок. При многопартийной продаже распределение позиции по партиям не должно дублировать сумму. Нулевой запас показывает отсутствие, но не размер потерянного спроса; нужны наблюдения спроса/доступности.', 'etl': 'Предложи raw→staging→core→marts как вариант, не обязательную сложность. Для каждой загрузки нужны идентификатор источника/пакета, watermark или версия, правила дублей, удалений, поздних событий и повторной обработки. CDC возможно только при поддержке источника. Инкрементальная загрузка должна быть идемпотентной; предусмотри сверки с источником и журнал ошибок. Расписание/SLA/объемы выбираются из требований, не придумываются.'})

def dispatch(name, arguments):
    expected = {"catalog": "table", "rules": "topic", "check_design": "design"}
    if name not in expected:
        raise ValueError("Неизвестная функция")
    key = expected[name]
    if not isinstance(arguments, dict) or set(arguments) != {key}:
        raise ValueError(f"Ожидается только аргумент {key}")
    value = arguments[key]
    if name in ("catalog", "rules"):
        if not isinstance(value, str) or len(value) > 100:
            raise ValueError(f"{key}: короткая строка")
        if name == "catalog":
            if value == "all":
                return {"source": "учебные константы", "tables": deepcopy(CATALOG)}
            if value not in CATALOG:
                return {"error": "Таблица отсутствует в учебном каталоге", "available": list(CATALOG)}
            return {"source": "учебные константы", "table": value, **deepcopy(CATALOG[value])}
        if value not in RULES:
            return {"error": "Неизвестная тема", "available": list(RULES)}
        return {"source": "учебная памятка", "topic": value, "rule": RULES[value]}
    if not isinstance(value, dict) or set(value) != {"grain", "facts", "dimensions"}:
        raise ValueError("design: нужны ровно grain, facts, dimensions")
    if not isinstance(value["grain"], str) or len(value["grain"]) > 500:
        raise ValueError("grain: строка до 500 символов")
    for field in ("facts", "dimensions"):
        if not isinstance(value[field], list) or len(value[field]) > 30 or any(not isinstance(x, str) or not x.strip() or len(x) > 100 for x in value[field]):
            raise ValueError(f"{field}: до 30 непустых строк")
    errors = []
    if not value["grain"].strip():
        errors.append("Не задана гранулярность")
    if not value["facts"]:
        errors.append("Не заданы факты")
    if not value["dimensions"]:
        errors.append("Не заданы измерения")
    for field in ("facts", "dimensions"):
        if len(set(value[field])) != len(value[field]):
            errors.append(f"Дубликаты в {field}")
    return {"valid": not errors, "errors": errors, "scope": "Только структура макета; бизнес-смысл, SQL и реальные данные не проверены"}
