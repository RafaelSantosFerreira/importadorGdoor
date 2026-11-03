"""Teste de conexão com Firebird (DATAGES.FDB)."""

import firebirdsql

HOST = "localhost"
PORT = 3050
DATABASE = r"F:\jorgeFb\DATAGES.FDB"
USER = "SYSDBA"
PASSWORD = "masterkey"
CHARSET = "WIN1252"


def main() -> None:
    print(f"Conectando em {HOST}:{PORT} -> {DATABASE} ...")
    conn = firebirdsql.connect(
        host=HOST,
        port=PORT,
        database=DATABASE,
        user=USER,
        password=PASSWORD,
        charset=CHARSET,
    )
    try:
        cur = conn.cursor()
        cur.execute("SELECT CURRENT_USER FROM RDB$DATABASE")
        (usuario,) = cur.fetchone()
        print(f"OK — conectado como {usuario.strip()}")

        cur.execute(
            """
            SELECT COUNT(*)
            FROM RDB$RELATIONS
            WHERE RDB$SYSTEM_FLAG = 0
              AND RDB$VIEW_BLR IS NULL
            """
        )
        (qtd_tabelas,) = cur.fetchone()
        print(f"Tabelas de usuário: {qtd_tabelas}")
    finally:
        conn.close()
        print("Conexão encerrada.")


if __name__ == "__main__":
    main()
