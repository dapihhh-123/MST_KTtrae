
import sqlite3
import os

db_path = "backend.db"
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    # Try absolute path based on previous knowledge
    db_path = r"c:\Users\dapi\Desktop\MST_KTtrae\backend.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", [t[0] for t in tables])
    
    # Inspect oracle_task_versions
    table_name = "oracle_task_versions"
    if any(t[0] == table_name for t in tables):
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        print(f"\nColumns in {table_name}:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
            
    conn.close()
except Exception as e:
    print(f"Error: {e}")
