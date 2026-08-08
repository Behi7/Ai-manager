import sys
import traceback
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

try:
    import uvicorn

    print("Starting server with string import...")
    result = uvicorn.run("app.main:app", host="127.0.0.1", port=8000, app_dir=r"C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot", log_level="info")
    print(f"Server stopped with result: {result}")
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
