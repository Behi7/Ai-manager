import sys, asyncio
sys.path.insert(0, 'ai-crm-bot')
from app.service import handle_user_message

class FakeBot:
    async def send_message(self, chat_id, text):
        print('SEND_MESSAGE to', chat_id, '->', text[:200])

async def run():
    bot = FakeBot()
    user_id = 9999999999
    await handle_user_message(bot, user_id, '/start')

if __name__ == '__main__':
    asyncio.run(run())
