import csv
from pathlib import Path

import firebirdsql

CSV_PATH = Path(r"C:\Users\rscholant\Downloads\itens.csv")

conn = firebirdsql.connect(
    host="localhost",
    port=3050,
    database=r"F:\jorgeFb\DATAGES.FDB",
    user="SYSDBA",
    password="masterkey",
    charset="WIN1252",
)
cur = conn.cursor()

with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.reader(f, delimiter=";"))

codigos = [r[0].strip().zfill(6) for r in rows]
barras = [r[1].strip() for r in rows]

print(f"CSV códigos: {len(codigos)}")

# overlap por codigo
exist_cod = 0
for i in range(0, len(codigos), 500):
    chunk = codigos[i : i + 500]
    placeholders = ",".join("?" * len(chunk))
    cur.execute(f"SELECT COUNT(*) FROM ESTOQUE WHERE CODIGO IN ({placeholders})", chunk)
    exist_cod += cur.fetchone()[0]
print(f"Já existem por CODIGO: {exist_cod}")

# overlap por barras (não vazias)
barras_ok = [b for b in barras if b]
exist_bar = 0
for i in range(0, len(barras_ok), 500):
    chunk = barras_ok[i : i + 500]
    placeholders = ",".join("?" * len(chunk))
    cur.execute(f"SELECT COUNT(*) FROM ESTOQUE WHERE BARRAS IN ({placeholders})", chunk)
    exist_bar += cur.fetchone()[0]
print(f"Já existem por BARRAS: {exist_bar}")

# CEST
cur.execute("SELECT FIRST 5 * FROM RDB$RELATIONS WHERE TRIM(RDB$RELATION_NAME) CONTAINING 'CEST'")
print("relações cest:", [r[0].strip() if isinstance(r[0], str) else r[0] for r in cur.fetchall()])

try:
    cur.execute("SELECT COUNT(*) FROM CEST")
    print("CEST count:", cur.fetchone()[0])
    cur.execute("SELECT FIRST 3 * FROM CEST")
    print("CEST cols:", [d[0] for d in cur.description])
    print(cur.fetchall()[:3])
except Exception as e:
    print("CEST erro:", e)

conn.close()
