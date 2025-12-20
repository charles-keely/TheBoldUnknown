import os
from db_utils import get_db_cursor

schema_path = os.path.join(os.path.dirname(__file__), 'reset_status.sql')

with open(schema_path, 'r') as f:
    sql = f.read()

print("Resetting assembly status...")
with get_db_cursor() as cur:
    cur.execute(sql)
print("Reset complete.")

