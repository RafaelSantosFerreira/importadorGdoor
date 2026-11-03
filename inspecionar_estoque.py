"""Inspeciona constraints e campos NOT NULL de ESTOQUE."""

import firebirdsql

conn = firebirdsql.connect(
    host="localhost",
    port=3050,
    database=r"F:\jorgeFb\DATAGES.FDB",
    user="SYSDBA",
    password="masterkey",
    charset="WIN1252",
)
cur = conn.cursor()

print("=== Campos NOT NULL / com default ===")
cur.execute(
    """
    SELECT
        TRIM(rf.RDB$FIELD_NAME) AS campo,
        rf.RDB$NULL_FLAG AS not_null,
        TRIM(rf.RDB$DEFAULT_SOURCE) AS default_src,
        f.RDB$FIELD_TYPE,
        f.RDB$FIELD_LENGTH,
        f.RDB$FIELD_SCALE,
        f.RDB$CHARACTER_LENGTH
    FROM RDB$RELATION_FIELDS rf
    JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE
    WHERE TRIM(rf.RDB$RELATION_NAME) = 'ESTOQUE'
    ORDER BY rf.RDB$FIELD_POSITION
    """
)
for row in cur.fetchall():
    campo, nn, default, ftype, length, scale, charlen = row
    if nn or default:
        print(f"{campo}: NOT_NULL={nn} DEFAULT={default} type={ftype} len={length} scale={scale} char={charlen}")

print("\n=== Primary key / unique ===")
cur.execute(
    """
    SELECT TRIM(i.RDB$INDEX_NAME), i.RDB$UNIQUE_FLAG, TRIM(iseg.RDB$FIELD_NAME)
    FROM RDB$INDICES i
    JOIN RDB$INDEX_SEGMENTS iseg ON iseg.RDB$INDEX_NAME = i.RDB$INDEX_NAME
    WHERE TRIM(i.RDB$RELATION_NAME) = 'ESTOQUE'
    ORDER BY i.RDB$INDEX_NAME, iseg.RDB$FIELD_POSITION
    """
)
for row in cur.fetchall():
    print(row)

print("\n=== Max CODIGO ===")
cur.execute("SELECT MAX(CODIGO) FROM ESTOQUE")
print(cur.fetchone())

conn.close()
