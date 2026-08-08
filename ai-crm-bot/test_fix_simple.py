import sys
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

print("Step 1: Import fields")
from app import fields
print(f"FIELDS: {fields.FIELDS}")

print("\nStep 2: Update fields")
test_fields = [
    {'key': 'name', 'label': 'Имя', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': None},
]
fields.update_fields(test_fields)
print(f"Updated FIELDS: {fields.FIELDS}")

print("\nStep 3: Import prompts")
from app.prompts import talker_system_prompt
prompt = talker_system_prompt()
print(f"Prompt contains 'имя': {'имя' in prompt.lower()}")
print(f"Prompt contains 'name': {'name' in prompt.lower()}")

print("\n✅ Test completed")
