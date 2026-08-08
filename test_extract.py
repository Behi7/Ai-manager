import sys, asyncio
sys.path.insert(0, 'ai-crm-bot')
from app.service import run_extraction, create_conversation, append_message, AsyncSessionLocal

class FakeBot:
    async def send_message(self, chat_id, text):
        print('SEND_MESSAGE to', chat_id, '->', text[:400])

async def run():
    bot = FakeBot()
    user_id = 9999999999

    async with AsyncSessionLocal() as session:
        conversation = await create_conversation(session, user_id)
        print('Created conversation', conversation.id, 'state=', conversation.state)

        # Add a sample user message with the fields expected by the extractor
        sample = (
            "Меня зовут Иван Петров. Телефон: +998901234567. Адрес: ул. Ленина, 10. "
            "Площадь комнаты 25 кв.м. Бюджет около 150000 рублей."
        )
        await append_message(session, conversation, "user", sample)

        # Inspect extractor output directly for debugging
        from app.service import get_history
        from app import agents

        history = await get_history(session, conversation.id)
        extraction = await agents.extract(history)
        print('Extraction status:', extraction.status)
        print('Missing fields:', extraction.missing_fields)
        print('Invalid fields:', extraction.invalid_fields)
        print('Extracted values:')
        for field in extraction.model_dump():
            print(field, '->', extraction.model_dump().get(field))

        await run_extraction(bot, session, conversation)
        await session.commit()

if __name__ == '__main__':
    asyncio.run(run())
