import asyncio
from pathlib import Path
from app.config import settings
from app.db import init_db
import app.models  # noqa: F401

print('database_url', settings.database_url)
path = settings.database_url.replace('sqlite+aiosqlite:///', '', 1)
print('normalized', path)
print('exists_before', Path(path).exists())

async def main():
    await init_db()
    print('init_db done')
    print('exists_after', Path(path).exists())

asyncio.run(main())
