import sys
import asyncio
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

print("Step 1: Importing aiogram...")
from aiogram import Bot, Dispatcher

print("Step 2: Loading config...")
from app.config import settings

print("Step 3: Creating bot...")
bot = Bot(token=settings.telegram_bot_token)

print("Step 4: Creating dispatcher...")
dp = Dispatcher()

print("Step 5: Starting polling (this will run for 5 seconds)...")
async def test_polling():
    try:
        polling_task = asyncio.create_task(dp.start_polling(bot))
        print("Polling task created successfully")
        await asyncio.sleep(5)
        print("Test completed successfully")
        polling_task.cancel()
    except Exception as e:
        print(f"Error during polling: {e}")
        import traceback
        traceback.print_exc()

try:
    asyncio.run(test_polling())
except Exception as e:
    print(f"Fatal error: {e}")
    import traceback
    traceback.print_exc()
