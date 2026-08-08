# -*- coding: utf-8 -*-
"""
Скрипт для демонстрации логики работы с полями amoCRM
(без реального подключения к API)
"""
import json
from pathlib import Path

# Демонстрация дефолтных полей
print("="*80)
print("1. ДЕФОЛТНЫЕ ПОЛЯ (если не удалось загрузить из amoCRM)")
print("="*80)

DEFAULT_FIELDS = [
    {
        "key": "name",
        "label": "Имя",
        "type": "str",
        "required": True,
        "amo_target": "contact",
        "amo_field_id": None,
        "validation": None,
    },
    {
        "key": "phone",
        "label": "Номер телефона",
        "type": "str",
        "required": True,
        "amo_target": "contact",
        "amo_field_id": None,
        "validation": r"^\+998\d{9}$",
    },
    {
        "key": "address",
        "label": "Адрес",
        "type": "str",
        "required": True,
        "amo_target": "lead",
        "amo_field_id": 123456,
        "validation": None,
    },
    {
        "key": "sqm",
        "label": "Площадь комнаты, м²",
        "type": "float",
        "required": True,
        "amo_target": "lead",
        "amo_field_id": 123457,
        "validation": None,
    },
    {
        "key": "budget",
        "label": "Бюджет",
        "type": "str",
        "required": True,
        "amo_target": "lead",
        "amo_field_id": 123458,
        "validation": None,
    },
]

print("\nДефолтные поля:")
for i, field in enumerate(DEFAULT_FIELDS, 1):
    print(f"{i}. Ключ: {field['key']}")
    print(f"   Название: {field['label']}")
    print(f"   Тип: {field['type']}")
    print(f"   Обязательное: {field['required']}")
    print(f"   Цель в amoCRM: {field['amo_target']}")
    print(f"   ID поля в amoCRM: {field.get('amo_field_id')}")
    print()

print("\n" + "="*80)
print("2. ЧТО ПРОИСХОДИТ ПРИ GET ЗАПРОСЕ К AMOCRM")
print("="*80)

print("\nGET запросы к amoCRM API:")
print("1. GET /api/v4/contacts/custom_fields")
print("   → Получает список кастомных полей контактов")
print("2. GET /api/v4/leads/custom_fields")
print("   → Получает список кастомных полей сделок")
print("\nСтруктура ответа (пример):")
print("""
{
  "_embedded": {
    "custom_fields": [
      {
        "id": 123456,
        "name": "Адрес",
        "type": "text",
        "code": "ADDRESS"
      },
      {
        "id": 123457,
        "name": "Площадь",
        "type": "numeric",
        "code": "SQM"
      }
    ]
  }
}
""")

print("\n" + "="*80)
print("3. КАК ПРЕОБРАЗУЮТСЯ ДАННЫЕ ИЗ AMOCRM")
print("="*80)

print("\nЛогика генерации полей из amoCRM:")
print("1. Добавляются системные поля: name, phone")
print("2. Поля сделок с * в названии считаются обязательными")
print("3. Поля контактов (кроме PHONE) добавляются после сделок")
print("4. ID поля становится amo_field_id")
print("5. Формируется ключ вида: lead_{id} или contact_{id}")

print("\nПример преобразования:")
amo_field = {
    "id": 123456,
    "name": "*Адрес",
    "type": "text",
    "code": "ADDRESS"
}

generated_field = {
    "key": "lead_123456",
    "label": "Адрес",  # * убирается
    "type": "str",  # text → str
    "required": True,  # потому что есть *
    "amo_target": "lead",
    "amo_field_id": 123456,
    "validation": None,
}

print("\nИсходное поле из amoCRM:")
print(json.dumps(amo_field, indent=2, ensure_ascii=False))
print("\nСгенерированное поле:")
print(json.dumps(generated_field, indent=2, ensure_ascii=False))

print("\n" + "="*80)
print("4. КАК ФОРМИРУЕТСЯ PAYLOAD ДЛЯ ЗАПИСИ В AMOCRM")
print("="*80)

print("\nПри создании контакта:")
print("POST /api/v4/contacts")
print("Payload содержит:")
print("- name: имя контакта")
print("- custom_fields_values: массив кастомных полей")

print("\nПример payload для контакта:")
contact_payload = {
    "name": ["Иван Иванов"],
    "custom_fields_values": [
        {
            "field_id": 123456,
            "values": [{"value": "+998901234567"}]
        },
        {
            "field_code": "PHONE",
            "values": [{"value": "+998901234567"}]
        }
    ]
}
print(json.dumps(contact_payload, indent=2, ensure_ascii=False))

print("\nПри создании сделки:")
print("POST /api/v4/leads")
print("Payload содержит:")
print("- name: название сделки")
print("- _embedded.contacts: привязка к контакту")
print("- custom_fields_values: массив кастомных полей")

print("\nПример payload для сделки:")
lead_payload = {
    "name": ["Заявка: Иван Иванов"],
    "_embedded": {
        "contacts": [{"id": 12345}]
    },
    "custom_fields_values": [
        {
            "field_id": 123456,
            "values": [{"value": "Ташкент, ул. Примерная"}]
        },
        {
            "field_id": 123457,
            "values": [{"value": "50.5"}]
        }
    ]
}
print(json.dumps(lead_payload, indent=2, ensure_ascii=False))

print("\n" + "="*80)
print("5. ПОЛЯ ДЛЯ ЗАПОЛНЕНИЯ В CHAT-БОТЕ")
print("="*80)

print("\nБот собирает данные пользователя в словарь draft:")
draft = {
    "name": "Иван Иванов",
    "phone": "+998901234567",
    "lead_123456": "Ташкент, ул. Примерная",
    "lead_123457": 50.5,
    "lead_123458": "1000$",
}

print("\nDraft данных:")
print(json.dumps(draft, indent=2, ensure_ascii=False))

print("\nЗатем этот draft разбивается:")
print("- Поля с amo_target='contact' → в контакт")
print("- Поля с amo_target='lead' → в сделку")

print("\nКонтакт получает:")
contact_fields = {k: v for k, v in draft.items() if k in ["name", "phone"]}
print(json.dumps(contact_fields, indent=2, ensure_ascii=False))

print("\nСделка получает:")
lead_fields = {k: v for k, v in draft.items() if k.startswith("lead_")}
print(json.dumps(lead_fields, indent=2, ensure_ascii=False))

print("\n" + "="*80)
print("ИТОГ")
print("="*80)
print("\n1. GET запросы получают структуру полей из amoCRM")
print("2. Эта структура преобразуется в формат FIELDS")
print("3. Бот собирает данные пользователя по этим полям")
print("4. При отправке данные разбиваются на контакт и сделку")
print("5. Каждый объект отправляется отдельным POST запросом")
