import csv
from pathlib import Path

import firebirdsql

with open("produtos_20261103155732.csv", encoding="latin-1", newline="") as f:
    r = csv.reader(f, delimiter=";")
    headers = next(r)
    sample = next(r)

print("HEADERS", len(headers))
for i, h in enumerate(headers):
    val = sample[i] if i < len(sample) else ""
    print(f"{i:02d}|{h}|{val}")

conn = firebirdsql.connect(
    host="localhost",
    port=3050,
    database=r"F:\jorgeFb\DATAGES.FDB",
    user="SYSDBA",
    password="masterkey",
    charset="WIN1252",
)
cur = conn.cursor()
cur.execute(
    """
    SELECT TRIM(rf.RDB$FIELD_NAME),
           f.RDB$FIELD_TYPE,
           f.RDB$FIELD_LENGTH,
           f.RDB$CHARACTER_LENGTH,
           f.RDB$FIELD_SCALE,
           rf.RDB$NULL_FLAG
    FROM RDB$RELATION_FIELDS rf
    JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE
    WHERE TRIM(rf.RDB$RELATION_NAME) = 'ESTOQUE'
    ORDER BY rf.RDB$FIELD_POSITION
    """
)
print("===ESTOQUE===")
for row in cur.fetchall():
    print("|".join("" if x is None else str(x) for x in row))
conn.close()
