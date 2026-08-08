import sys
import traceback
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

try:
    print("Testing the fix...")

    # 1. Simulate startup
    from app import fields
    from app.prompts import talker_system_prompt

    print(f"Initial FIELDS: {fields.FIELDS}")
    prompt1 = talker_system_prompt()
    print(f"Initial prompt has fields: {'имя' in prompt1.lower()}")

    # 2. Update fields (simulating startup)
    test_fields = [
        {'key': 'name', 'label': 'Имя', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': None},
        {'key': 'phone', 'label': 'Номер телефона', 'type': 'str', 'required': True, 'amo_target': 'contact', 'amo_field_id': None, 'validation': r'^\+998\d{9}$'},
    ]

    fields.update_fields(test_fields)
    print(f"Updated FIELDS: {fields.FIELDS}")

    # 3. Check if prompt now has fields
    prompt = talker_system_prompt()
    print(f"Updated prompt has fields: {'имя' in prompt.lower()}")
    print(f"Updated prompt has phone: {'телефон' in prompt.lower()}")

    # 4. Test with extractor
    from app.prompts import extractor_system_prompt
    extractor_prompt = extractor_system_prompt()
    print(f"Extractor prompt has fields: {'name' in extractor_prompt.lower()}")
    print(f"Extractor prompt has phone: {'phone' in extractor_prompt.lower()}")

    print("\n✅ Fix working correctly!")
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
