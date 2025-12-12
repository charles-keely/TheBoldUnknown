import psycopg2
from photo_researcher.config import config

conn = psycopg2.connect(
    host=config.POSTGRES_HOST,
    port=config.POSTGRES_PORT,
    dbname=config.POSTGRES_DB,
    user=config.POSTGRES_USER,
    password=config.POSTGRES_PASSWORD
)

cur = conn.cursor()
cur.execute("""
    SELECT count(*) 
    FROM story_research sr
    WHERE sr.status = 'completed'
    AND (
        SELECT count(*) 
        FROM story_photos sp 
        WHERE sp.story_research_id = sr.id 
        AND sp.status = 'approved'
    ) < 2
""")
count = cur.fetchone()[0]
print(f"Stories waiting for photos: {count}")

cur.execute("""
    SELECT l.title 
    FROM story_research sr
    JOIN leads l ON sr.lead_id = l.id
    WHERE sr.status = 'completed'
""")
titles = cur.fetchall()
print("\nCompleted stories available:")
for t in titles:
    print(f"- {t[0]}")

conn.close()

