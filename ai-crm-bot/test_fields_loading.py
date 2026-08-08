import sys
import asyncio
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

def log(msg):
    print(msg)
    sys.stdout.flush()

async def test_fields_loading():
    from app.service import generate_fields_from_amocrm
    from app import fields
    
    log("Testing fields loading from amoCRM...")
    fields_data = await generate_fields_from_amocrm()
    
    log(f"\nTotal fields loaded: {len(fields_data)}")
    log("\nFields details:")
    for field in fields_data:
        log(f"  - {field['key']}: {field['label']} (target: {field['amo_target']}, required: {field['required']})")
    
    # Update fields
    fields.update_fields(fields_data)
    
    # Check prompts
    from app.prompts import talker_system_prompt, extractor_system_prompt
    
    log("\nTalker prompt fields:")
    talker_prompt = talker_system_prompt()
    log(f"  Contains 'имя': {'имя' in talker_prompt.lower()}")
    log(f"  Contains 'телефон': {'телефон' in talker_prompt.lower()}")
    log(f"  Contains 'площадь': {'площадь' in talker_prompt.lower()}")
    log(f"  Contains 'адрес': {'адрес' in talker_prompt.lower()}")
    
    log("\nExtractor prompt fields:")
    extractor_prompt = extractor_system_prompt()
    log(f"  Contains 'name': {'name' in extractor_prompt.lower()}")
    log(f"  Contains 'phone': {'phone' in extractor_prompt.lower()}")
    log(f"  Total field definitions: {extractor_prompt.count('- ')}")
    
    log("\n✅ Test completed successfully")

asyncio.run(test_fields_loading())
