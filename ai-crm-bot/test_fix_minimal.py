import sys
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

from app import fields
from app.prompts import talker_system_prompt

# Update fields
test_fields = [{'key': 'name', 'label': 'Имя', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': None}]
fields.update_fields(test_fields)

# Test prompt
prompt = talker_system_prompt()
print("SUCCESS" if 'имя' in prompt.lower() else "FAIL")
