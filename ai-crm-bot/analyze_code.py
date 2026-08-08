"""
Анализ кода для понимания что происходит при GET запросах к amoCRM
"""
import re
from pathlib import Path

print("="*80)
print("АНАЛИЗ КОДА ВЗАИМОДЕЙСТВИЯ С AMOCRM")
print("="*80)

print("\n1. ФАЙЛ: app/amo.py")
print("-" * 80)

# Читаем файл amo.py
amo_file = Path("app/amo.py")
if amo_file.exists():
    content = amo_file.read_text(encoding='utf-8')
    
    # Находим все GET запросы
    get_requests = re.findall(r'["\']GET["\'],\s*["\']([^"\']+)["\']', content)
    
    print("\nНайденные GET запросы к amoCRM API:")
    for i, endpoint in enumerate(get_requests, 1):
        print(f"{i}. {endpoint}")
        if "contacts" in endpoint:
            print("   → Запрос данных контактов")
        elif "leads" in endpoint:
            print("   → Запрос данных сделок")
        if "custom_fields" in endpoint:
            print("   → Получение кастомных полей")
    
    # Находим методы классов
    methods = re.findall(r'async def (\w+)\(self[^)]*\):', content)
    print(f"\nМетоды класса AmoCRMClient ({len(methods)}):")
    for i, method in enumerate(methods, 1):
        print(f"{i}. {method}()")

print("\n2. ФАЙЛ: app/service.py")
print("-" * 80)

service_file = Path("app/service.py")
if service_file.exists():
    content = service_file.read_text(encoding='utf-8')
    
    # Находим функцию generate_fields_from_amocrm
    if "generate_fields_from_amocrm" in content:
        print("\nФункция generate_fields_from_amocrm найдена")
        
        # Извлекаем логику
        start = content.find("async def generate_fields_from_amocrm")
        end = content.find("\n\nasync def", start + 1)
        if end == -1:
            end = len(content)
        
        function_code = content[start:end]
        
        print("\nКлючевые шаги функции:")
        steps = [
            "1. Вызов amo_client.get_account_custom_fields()",
            "2. Добавление системных полей (name, phone)",
            "3. Обработка полей сделок (leads)",
            "4. Обработка полей контактов (contacts)",
            "5. Преобразование в формат FIELDS",
            "6. Возврат сгенерированных полей"
        ]
        for step in steps:
            print(f"  {step}")

print("\n3. ФАЙЛ: app/fields.py")
print("-" * 80)

fields_file = Path("app/fields.py")
if fields_file.exists():
    content = fields_file.read_text(encoding='utf-8')
    
    if "DEFAULT_FIELDS" in content:
        print("\nНайдены дефолтные поля (DEFAULT_FIELDS)")
        
        # Извлекаем DEFAULT_FIELDS
        start = content.find("DEFAULT_FIELDS = [")
        end = content.find("]", start) + 1
        if start != -1 and end != -1:
            default_fields = content[start:end]
            print("\nСтруктура DEFAULT_FIELDS:")
            print(default_fields[:500] + "...")

print("\n4. ПОТОК ДАННЫХ ПРИ ЗАПУСКЕ ПРИЛОЖЕНИЯ")
print("-" * 80)

print("""
1. main.py → lifespan()
   ↓
2. service.py → generate_fields_from_amocrm()
   ↓
3. amo.py → get_account_custom_fields()
   ├─→ GET /api/v4/contacts/custom_fields
   └─→ GET /api/v4/leads/custom_fields
   ↓
4. Обработка и генерация структуры полей
   ├─→ Системные поля (name, phone)
   ├─→ Поля сделок (с приоритетом обязательных *)
   └─→ Поля контактов
   ↓
5. fields.py → update_fields()
   ├─→ Обновление глобальной переменной FIELDS
   └─→ Обновление глобальной переменной FIELD_BY_KEY
   ↓
6. Приложение готово к работе с полями
""")

print("\n5. ПОТОК ДАННЫХ ПРИ СОЗДАНИИ КОНТАКТА/СДЕЛКИ")
print("-" * 80)

print("""
1. Пользователь вводит данные в чат-боте
   ↓
2. Данные собираются в словарь draft
   {
     "name": "Иван",
     "phone": "+998...",
     "lead_123456": "Адрес",
     "lead_123457": 50.5
   }
   ↓
3. amo.py → create_contact(draft)
   ├─→ _contact_payload(draft)
   │  ├─→ name → payload["name"]
   │  └─→ custom_fields → payload["custom_fields_values"]
   └─→ POST /api/v4/contacts
   ↓
4. amo.py → create_lead(draft, contact_id)
   ├─→ _lead_payload(draft, contact_id)
   │  ├─→ name → payload["name"]
   │  ├─→ contact_id → payload["_embedded"]["contacts"]
   │  └─→ custom_fields → payload["custom_fields_values"]
   └─→ POST /api/v4/leads
""")

print("\n6. СООТВЕТСТВИЕ ПОЛЕЙ")
print("-" * 80)

print("""
Ключ в draft          → Поле в amoCRM
─────────────────────────────────────────
name                  → contact.name (системное)
phone                 → contact.custom_fields_values (field_code=PHONE)
lead_{field_id}       → lead.custom_fields_values (field_id={field_id})
contact_{field_id}    → contact.custom_fields_values (field_id={field_id})

Пример:
draft["lead_123456"]  → lead.custom_fields_values[0].field_id = 123456
                      → lead.custom_fields_values[0].values[0].value = "адрес"
""")

print("\n" + "="*80)
print("АНАЛИЗ ЗАВЕРШЕН")
print("="*80)
