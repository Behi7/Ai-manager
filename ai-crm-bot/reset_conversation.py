import asyncio
from sqlalchemy import select, update
from app.db import AsyncSessionLocal
from app.models import Conversation, TelegramContact

async def reset_user_conversation(user_id: int = None):
    """
    Сбрасывает состояние conversation для пользователя или всех пользователей
    """
    async with AsyncSessionLocal() as session:
        if user_id:
            # Сброс для конкретного пользователя
            stmt = (
                update(Conversation)
                .where(Conversation.telegram_user_id == user_id)
                .values(
                    state="COLLECTING",
                    human_takeover=False,
                    retry_count=0,
                    field_retry_count={}
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            print(f"Updated {result.rowcount} conversations for user {user_id}")
        else:
            # Сброс для всех пользователей
            stmt = (
                update(Conversation)
                .values(
                    state="COLLECTING",
                    human_takeover=False,
                    retry_count=0,
                    field_retry_count={}
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            print(f"Updated {result.rowcount} conversations for all users")

async def show_conversations():
    """Показывает все conversations в базе"""
    async with AsyncSessionLocal() as session:
        stmt = select(Conversation)
        result = await session.execute(stmt)
        conversations = result.scalars().all()
        
        print(f"Total conversations: {len(conversations)}")
        for conv in conversations:
            print(f"User ID: {conv.telegram_user_id}, State: {conv.state}, Human takeover: {conv.human_takeover}")

async def main():
    print("Current conversations:")
    await show_conversations()
    
    print("\nResetting all conversations...")
    await reset_user_conversation()
    
    print("\nAfter reset:")
    await show_conversations()

if __name__ == "__main__":
    asyncio.run(main())
