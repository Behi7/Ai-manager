import asyncio
from pathlib import Path
from app.config import settings
from app.db import AsyncSessionLocal, engine
from app.models import Conversation  # Import your models
from sqlalchemy import text

# Get the database file path from settings
db_path = settings.database_url.replace('sqlite+aiosqlite:///', '', 1)
print(f'Database path: {db_path}')
print(f'Exists: {Path(db_path).exists()}')

async def main():
    async with AsyncSessionLocal() as session:
        # Show current conversations
        print("\nCurrent conversations:")
        result = await session.execute(
            text("SELECT telegram_user_id, state, human_takeover FROM conversations")
        )
        rows = result.fetchall()
        for row in rows:
            print(f"User ID: {row[0]}, State: {row[1]}, Human takeover: {row[2]}")

        # Reset all conversations
        print("\nResetting all conversations...")
        await session.execute(
            text("""
                UPDATE conversations 
                SET state = 'COLLECTING', 
                    human_takeover = 0, 
                    retry_count = 0, 
                    field_retry_count = '{}'
            """)
        )
        await session.commit()
        print("Reset complete")

        # Show after reset
        print("\nAfter reset:")
        result = await session.execute(
            text("SELECT telegram_user_id, state, human_takeover FROM conversations")
        )
        rows = result.fetchall()
        for row in rows:
            print(f"User ID: {row[0]}, State: {row[1]}, Human takeover: {row[2]}")

    print("\nDone!")

asyncio.run(main())
