"""Lista tabelas e estrutura relacionadas a estoque."""

import firebirdsql

conn = firebirdsql.connect(
    host="localhost",
    port=3050,
    database=r"F:\jorgeFb\DATAGES.FDB",
    user="SYSDBA",
    password="masterkey",
    charset="UTF8",
)
cur = conn.cursor()

print("=== Tabelas com ESTOQUE / PRODUTO / STOCK / INVENT ===")
cur.execute(
    """
    SELECT TRIM(RDB$RELATION_NAME)
    FROM RDB$RELATIONS
    WHERE RDB$SYSTEM_FLAG = 0
      AND RDB$VIEW_BLR IS NULL
      AND (
           UPPER(RDB$RELATION_NAME) CONTAINING 'ESTOQUE'
        OR UPPER(RDB$RELATION_NAME) CONTAINING 'STOCK'
        OR UPPER(RDB$RELATION_NAME) CONTAINING 'PRODUTO'
        OR UPPER(RDB$RELATION_NAME) CONTAINING 'INVENT'
      )
    ORDER BY 1
    """
)
tabelas = [r[0] for r in cur.fetchall()]
for t in tabelas:
    print(t)

for t in tabelas:
    if "ESTOQUE" in t.upper() or t.upper() in ("PRODUTOS", "PRODUTO"):
        print(f"\n=== Colunas de {t} ===")
        cur.execute(
            """
            SELECT TRIM(rf.RDB$FIELD_NAME),
                   TRIM(f.RDB$FIELD_TYPE),
                   f.RDB$FIELD_LENGTH,
                   f.RDB$FIELD_SCALE
            FROM RDB$RELATION_FIELDS rf
            JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE
            WHERE TRIM(rf.RDB$RELATION_NAME) = ?
            ORDER BY rf.RDB$FIELD_POSITION
            """,
            (t,),
        )
        for nome, ftype, length, scale in cur.fetchall():
            print(f"  {nome} | type={ftype} len={length} scale={scale}")

        print(f"\n=== Amostra {t} (5 linhas) ===")
        try:
            cur.execute(f'SELECT FIRST 5 * FROM "{t}"')
            cols = [d[0] for d in cur.description]
            print(" | ".join(cols))
            for row in cur.fetchall():
                print(" | ".join(str(v) if v is not None else "" for v in row))
        except Exception as e:
            print(f"erro amostra: {e}")

conn.close()
