# Поля загружаются только из amoCRM. Если не загрузились - приложение не работает.
# Используем простые глобальные переменные - они будут обновлены через update_fields
FIELDS = []
FIELD_BY_KEY = {}


def update_fields(new_fields: list[dict]) -> None:
    """Обновляет FIELDS и FIELD_BY_KEY новыми данными из AmoCRM"""
    global FIELDS, FIELD_BY_KEY
    if not new_fields:
        raise ValueError("Не удалось загрузить поля из amoCRM - приложение не может работать без полей")
    FIELDS = new_fields
    FIELD_BY_KEY = {field["key"]: field for field in FIELDS}
    print(f"UPDATED FIELDS: {len(FIELDS)} fields")  # Для отладки
