import sys
import traceback
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

try:
    print("Step 1: Importing uvicorn...")
    import uvicorn
    
    print("Step 2: Importing app.main...")
    from app.main import app
    
    print("Step 3: Starting server...")
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    try:
        # Use the app object directly
        result = uvicorn.run(app, host="127.0.0.1", port=8000, log_level="debug")
        print(f"Server stopped with result: {result}")
    except Exception as e:
        print(f"Uvicorn error: {e}")
        traceback.print_exc()
        
except Exception as e:
    print(f"Import error: {e}")
    traceback.print_exc()
