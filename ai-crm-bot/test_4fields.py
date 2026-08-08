import sys
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

from app import fields
test_fields = [
    {'key': 'name', 'label': 'Имя', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': None},
    {'key': 'phone', 'label': 'Номер телефона', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': r'^\+998\d{9}$'},
    {'key': 'lead_999069', 'label': 'Площадь', 'type': 'str', 'required': True, 'amo_target': 'lead', 'amo_field_id': 999069, 'validation': None},
    {'key': 'lead_999071', 'label': 'Адрес', 'type': 'str', 'required': True, 'amo_target': 'lead', 'amo_field_id': 999071, 'validation': None},
]
fields.update_fields(test_fields)
print(f"✅ SUCCESS - {len(fields.FIELDS)} fields loaded")
