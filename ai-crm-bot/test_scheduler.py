import sys
import traceback
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

try:
    from app.config import settings
    from aiogram import Bot
    from app.scheduler import start_scheduler
    
    print("Creating bot...")
    bot = Bot(token=settings.telegram_bot_token)
    
    print("Starting scheduler...")
    start_scheduler(bot)
    print("Scheduler started successfully")
    
    import time
    time.sleep(5)
    print("Scheduler test completed")
    
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
