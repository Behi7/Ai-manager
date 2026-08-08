import sys
import asyncio
import traceback
sys.path.insert(0, r'C:\Users\user\Desktop\срм\Ai_manager_2.0\ai-crm-bot')

try:
    print("Step 1: Importing app.main...")
    from app.main import app
    print("Step 2: App created successfully")
    print(f"App type: {type(app)}")
    print(f"App routes: {[route.path for route in app.routes]}")
    
    # Test lifespan manually
    print("Step 3: Testing lifespan...")
    async def test_lifespan():
        async with app.router.lifespan_context(app):
            print("Lifespan started successfully")
            await asyncio.sleep(1)
            print("Lifespan test passed")
    
    asyncio.run(test_lifespan())
    print("Step 4: Lifespan test completed")
    
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
