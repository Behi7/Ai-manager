import sys
import traceback
import logging
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

logging.basicConfig(level=logging.DEBUG)

try:
    from app.main import app
    import uvicorn
    
    print("Starting minimal server...")
    print(f"App object: {app}")
    print(f"App type: {type(app)}")
    
    # Try running with timeout to prevent immediate exit
    import threading
    import time
    
    def run_server():
        result = uvicorn.run(app, host="127.0.0.1", port=8000, log_level="debug")
        print(f"Server stopped with result: {result}")
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Keep the main thread alive
    print("Server thread started, keeping main thread alive...")
    while server_thread.is_alive():
        time.sleep(1)
        
    print("Server thread exited")
    
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
