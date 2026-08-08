import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.service import handle_user_message

class FakeBot:
    async def send_message(self, *args, **kwargs):
        print('send_message called', args, kwargs)
        return None

async def main():
    try:
        await handle_user_message(FakeBot(), 999999, 'привет')
        print('done')
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
