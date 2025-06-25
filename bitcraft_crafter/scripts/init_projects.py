import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "bitcraft.db"))
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Add Projects table (if not exists)
cursor.execute('''
CREATE TABLE IF NOT EXISTS Projects (
    ProjectID INTEGER PRIMARY KEY AUTOINCREMENT,
    Name TEXT NOT NULL,
    Description TEXT,
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Add ProjectItems table (if not exists)
cursor.execute('''
CREATE TABLE IF NOT EXISTS ProjectItems (
    ProjectItemID INTEGER PRIMARY KEY AUTOINCREMENT,
    ProjectID INTEGER,
    ItemName TEXT NOT NULL,
    Tier TEXT,
    Quantity INTEGER,
    FOREIGN KEY (ProjectID) REFERENCES Projects(ProjectID)
)
''')

conn.commit()
conn.close()
print("✅ Projects tables created or verified.")
