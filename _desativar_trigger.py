"""Tenta desativar TR_ESTOQUE_BARRAS sem passar pela BLR da FN_VALIDA_BARCODE."""

from db import conectar


def status(cur):
    cur.execute(
        """
        SELECT RDB$TRIGGER_INACTIVE
        FROM RDB$TRIGGERS
        WHERE TRIM(RDB$TRIGGER_NAME) = 'TR_ESTOQUE_BARRAS'
        """
    )
    row = cur.fetchone()
    return row[0] if row else None


conn = conectar()
cur = conn.cursor()
print("Antes inactive=", status(cur))

# 1) update direto no sistema (Firebird clássico)
try:
    cur.execute(
        """
        UPDATE RDB$TRIGGERS
        SET RDB$TRIGGER_INACTIVE = 1
        WHERE TRIM(RDB$TRIGGER_NAME) = 'TR_ESTOQUE_BARRAS'
        """
    )
    conn.commit()
    print("UPDATE RDB$TRIGGERS ok, inactive=", status(cur))
except Exception as e:
    print("UPDATE sistema falhou:", e)
    try:
        conn.rollback()
    except Exception:
        pass

# se ainda ativa, tenta DROP
if status(cur) == 0:
    try:
        cur.execute("DROP TRIGGER TR_ESTOQUE_BARRAS")
        conn.commit()
        print("DROP TRIGGER ok")
    except Exception as e:
        print("DROP falhou:", e)

conn.close()

conn = conectar()
cur = conn.cursor()
cur.execute(
    """
    SELECT TRIM(RDB$TRIGGER_NAME), RDB$TRIGGER_INACTIVE
    FROM RDB$TRIGGERS
    WHERE TRIM(RDB$TRIGGER_NAME) = 'TR_ESTOQUE_BARRAS'
    """
)
print("Final:", cur.fetchone())
conn.close()
