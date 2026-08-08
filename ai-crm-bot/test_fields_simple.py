import sys
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

from app import fields
print(f"Initial FIELDS: {fields.FIELDS}")

test_fields = [
    {'key': 'name', 'label': 'Имя', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': None},
]

fields.update_fields(test_fields)
print(f"After update FIELDS: {fields.FIELDS}")

# Test direct import
from app.fields import FIELDS
print(f"Direct import FIELDS: {FIELDS}")

# Test another import
from app import fields as fields2
print(f"Second import FIELDS: {fields2.FIELDS}")
