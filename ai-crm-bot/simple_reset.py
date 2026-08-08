import sqlite3

# Connect to the database
conn = sqlite3.connect('ai_crm.db')
cursor = conn.cursor()

# Show current conversations
print("Current conversations:")
cursor.execute("SELECT telegram_user_id, state, human_takeover FROM conversations")
rows = cursor.fetchall()
for row in rows:
    print(f"User ID: {row[0]}, State: {row[1]}, Human takeover: {row[2]}")

# Reset all conversations
print("\nResetting all conversations...")
cursor.execute("""
    UPDATE conversations 
    SET state = 'COLLECTING', 
        human_takeover = 0, 
        retry_count = 0, 
        field_retry_count = '{}'
""")
print(f"Updated {cursor.rowcount} rows")

conn.commit()

# Show after reset
print("\nAfter reset:")
cursor.execute("SELECT telegram_user_id, state, human_takeover FROM conversations")
rows = cursor.fetchall()
for row in rows:
    print(f"User ID: {row[0]}, State: {row[1]}, Human takeover: {row[2]}")

conn.close()
print("Done!")
