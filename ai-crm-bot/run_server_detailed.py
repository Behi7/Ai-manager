import sys
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

try:
    import uvicorn
    from app.main import app
    print("Starting server...")
    import logging
    logging.basicConfig(level=logging.DEBUG)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="debug")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
