"""
Тестовый скрипт для проверки получения полей из amoCRM
"""
import asyncio
import logging
import sys
from pathlib import Path

# Добавляем путь к app директории
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings
from app.amo import AmoCRMClient
from app.service import generate_fields_from_amocrm
from app.fields import FIELDS

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


async def test_amocrm_fields():
    """Тест получения полей из amoCRM"""
    
    if not settings.amo_base_url or not settings.amo_token:
        logger.error("amoCRM не настроен. Проверьте AMO_BASE_URL и AMO_TOKEN в .env")
        return
    
    amo_client = AmoCRMClient()
    
    print("\n" + "="*80)
    print("1. ПОЛУЧЕНИЕ СЫРЫХ ДАННЫХ ИЗ AMOCRM")
    print("="*80)
    
    try:
        # Получаем кастомные поля
        custom_fields = await amo_client.get_account_custom_fields()
        
        print(f"\nПолучены кастомные поля:")
        print(f"  - Контактов: {len(custom_fields.get('contacts', []))}")
        print(f"  - Сделок: {len(custom_fields.get('leads', []))}")
        
        # Выводим детали полей контактов
        print("\n--- Поля контактов ---")
        for i, field in enumerate(custom_fields.get('contacts', [])[:10], 1):
            print(f"{i}. ID: {field.get('id')}")
            print(f"   Название: {field.get('name')}")
            print(f"   Код: {field.get('code')}")
            print(f"   Тип: {field.get('type')}")
            print()
        
        # Выводим детали полей сделок
        print("\n--- Поля сделок ---")
        for i, field in enumerate(custom_fields.get('leads', [])[:10], 1):
            print(f"{i}. ID: {field.get('id')}")
            print(f"   Название: {field.get('name')}")
            print(f"   Код: {field.get('code')}")
            print(f"   Тип: {field.get('type')}")
            print()
            
    except Exception as e:
        logger.error(f"Ошибка при получении полей: {e}")
        return
    
    print("\n" + "="*80)
    print("2. ГЕНЕРАЦИЯ ПОЛЕЙ ДЛЯ ЗАПОЛНЕНИЯ")
    print("="*80)
    
    try:
        # Генерируем поля
        fields = await generate_fields_from_amocrm()
        
        print(f"\nСгенерировано {len(fields)} полей (все, без лимита):")
        print()
        
        for i, field in enumerate(fields, 1):
            print(f"{i}. Ключ: {field['key']}")
            print(f"   Название: {field['label']}")
            print(f"   Тип: {field['type']}")
            print(f"   Обязательное: {field['required']}")
            print(f"   Цель (amo_target): {field['amo_target']}")
            print(f"   ID поля в amoCRM: {field.get('amo_field_id')}")
            print(f"   Валидация: {field.get('validation')}")
            print()
            
    except Exception as e:
        logger.error(f"Ошибка при генерации полей: {e}")
        return
    
    print("\n" + "="*80)
    print("3. ТЕСТОВЫЙ ЗАПРОС КОНТАКТА")
    print("="*80)
    
    # Пример того, как будет выглядеть draft при создании контакта
    test_draft = {
        "name": "Тестовый клиент",
        "phone": "+998901234567",
    }
    
    # Добавляем сгенерированные поля
    for field in fields:
        if field['key'] not in ['name', 'phone']:
            if field['type'] == 'str':
                test_draft[field['key']] = f"Тестовое значение для {field['label']}"
            elif field['type'] == 'float':
                test_draft[field['key']] = 100.0
            elif field['type'] == 'bool':
                test_draft[field['key']] = True
    
    print("\nТестовый draft данных:")
    import json
    print(json.dumps(test_draft, indent=2, ensure_ascii=False))
    
    print("\n" + "="*80)
    print("4. ФОРМИРОВАНИЕ PAYLOAD ДЛЯ AMOCRM")
    print("="*80)
    
    # Формируем payload для контакта
    contact_payload = amo_client._contact_payload(test_draft)
    print("\nPayload для создания контакта:")
    print(json.dumps(contact_payload, indent=2, ensure_ascii=False))
    
    print("\n" + "="*80)
    print("ТЕСТ ЗАВЕРШЕН")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(test_amocrm_fields())
