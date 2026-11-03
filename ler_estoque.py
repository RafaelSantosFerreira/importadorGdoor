"""Lê a tabela ESTOQUE do Firebird (DATAGES.FDB)."""

import firebirdsql

HOST = "localhost"
PORT = 3050
DATABASE = r"F:\jorgeFb\DATAGES.FDB"
USER = "SYSDBA"
PASSWORD = "masterkey"
CHARSET = "WIN1252"

# Campos principais para migração de produtos/estoque
CAMPOS = """
    CODIGO,
    BARRAS,
    DESCRICAO,
    UND,
    FAMILIA,
    GRUPO,
    FORNECEDOR,
    QTD,
    QTD_DISPONIVEL,
    QTD_RESERVADA,
    PRECO_CUSTO,
    CUSTO_MEDIO,
    PRECO_VENDA,
    PRECO_ATACADO,
    COD_NCM,
    COD_CEST,
    SITUACAO,
    DATA_CADASTRO,
    DELETED_AT
"""


def conectar():
    return firebirdsql.connect(
        host=HOST,
        port=PORT,
        database=DATABASE,
        user=USER,
        password=PASSWORD,
        charset=CHARSET,
    )


def main() -> None:
    conn = conectar()
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM ESTOQUE WHERE DELETED_AT IS NULL")
        (total,) = cur.fetchone()
        print(f"Registros ativos em ESTOQUE: {total}")

        cur.execute(
            f"""
            SELECT FIRST 20
                {CAMPOS}
            FROM ESTOQUE
            WHERE DELETED_AT IS NULL
            ORDER BY CODIGO
            """
        )
        cols = [d[0].strip() for d in cur.description]
        print(" | ".join(cols))
        for row in cur.fetchall():
            vals = []
            for v in row:
                if v is None:
                    vals.append("")
                elif isinstance(v, bytes):
                    vals.append("")
                else:
                    vals.append(str(v).strip() if isinstance(v, str) else str(v))
            print(" | ".join(vals))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
