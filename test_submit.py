import sys, asyncio
sys.path.insert(0, 'ai-crm-bot')
from app.service import submit_to_crm, create_conversation, append_message, AsyncSessionLocal

class FakeBot:
    async def send_message(self, chat_id, text):
        print('SEND_MESSAGE to', chat_id, '->', text[:400])

async def run():
    bot = FakeBot()
    user_id = 9999999998

    async with AsyncSessionLocal() as session:
        conversation = await create_conversation(session, user_id)
        # prepare a complete draft matching FIELDS
        draft = {
            'name': 'Тест Пользователь',
            'phone': '+998901234568',
            'address': 'ул. Примерная, 1',
            'sqm': 30.0,
            'budget': '100000 рублей',
        }
        conversation.draft_json = draft
        await session.flush()

        print('Submitting draft for conversation', conversation.id)
        await submit_to_crm(bot, session, conversation)
        await session.commit()

if __name__ == '__main__':
    asyncio.run(run())
