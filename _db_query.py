import sqlite3, os
db=os.path.join(os.path.dirname(os.path.abspath(__file__)),"database.db")
conn=sqlite3.connect(db)
conn.row_factory=sqlite3.Row
c=conn.cursor()
print("=== ALL TABLES ===")
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables=[t[0] for t in c.fetchall()]
for t in tables:print(t)
print()
print("=== FULL SCHEMA ===")
c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL ORDER BY name")
for row in c.fetchall():
    print(row[0])
    print()
for tbl in tables:
    print(f"=== DATA: {tbl} ===")
    try:
        c.execute(f"SELECT * FROM [{tbl}]")
        cols=[d[0] for d in c.description]
        print(f"Columns: {cols}")
        rows=c.fetchall()
        print(f"Row count: {len(rows)}")
        for row in rows[:50]:print(dict(row))
    except Exception as e:print(f"Error: {e}")
    print()
conn.close()
