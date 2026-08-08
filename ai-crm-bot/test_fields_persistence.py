import sys
import os
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

# Add flush to ensure output
def log(msg):
    print(msg)
    sys.stdout.flush()

log("Step 1: Import fields module")
from app import fields

log(f"Initial FIELDS: {fields.FIELDS}")
log(f"Initial FIELD_BY_KEY: {fields.FIELD_BY_KEY}")

log("\nStep 2: Update fields")
test_fields = [
    {'key': 'name', 'label': 'Имя', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': None},
    {'key': 'phone', 'label': 'Номер телефона', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': r'^\+998\d{9}$'},
]

fields.update_fields(test_fields)

log(f"After update FIELDS: {fields.FIELDS}")
log(f"After update FIELD_BY_KEY: {fields.FIELD_BY_KEY}")

log("\nStep 3: Import fields again (simulating module reload)")
from app import fields as fields2

log(f"Second import FIELDS: {fields2.FIELDS}")
log(f"Second import FIELD_BY_KEY: {fields2.FIELD_BY_KEY}")

log("\nStep 4: Import fields.FIELDS directly")
from app.fields import FIELDS as FIELDS_direct

log(f"Direct import FIELDS: {FIELDS_direct}")

log("\nStep 5: Import fields module again")
import app.fields as fields3

log(f"Third import FIELDS: {fields3.FIELDS}")
log(f"Are they the same object? {fields.FIELDS is fields3.FIELDS}")
