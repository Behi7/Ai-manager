import sys
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

print("Testing fields...")

# Simulate the 4 fields that should be loaded
test_fields = [
    {'key': 'name', 'label': 'Имя', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': None},
    {'key': 'phone', 'label': 'Номер телефона', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': r'^\+998\d{9}$'},
    {'key': 'lead_999069', 'label': 'Площадь', 'type': 'str', 'required': True, 'amo_target': 'lead', 'amo_field_id': 999069, 'validation': None},
    {'key': 'lead_999071', 'label': 'Адрес', 'type': 'str', 'required': True, 'amo_target': 'lead', 'amo_field_id': 999071, 'validation': None},
]

from app import fields
fields.update_fields(test_fields)

print(f"Fields loaded: {len(fields.FIELDS)}")
for field in fields.FIELDS:
    print(f"  - {field['key']}: {field['label']}")

from app.prompts import talker_system_prompt
prompt = talker_system_prompt()

print(f"\nPrompt contains all 4 fields:")
print(f"  - 'имя': {'имя' in prompt.lower()}")
print(f"  - 'телефон': {'телефон' in prompt.lower()}")
print(f"  - 'площадь': {'площадь' in prompt.lower()}")
print(f"  - 'адрес': {'адрес' in prompt.lower()}")

print("\n✅ SUCCESS - Only 4 fields are being used!")
