from __future__ import annotations

import re

import firebirdsql

from config import CAMPOS_IGNORADOS
from conexao_store import carregar as carregar_conexao

_TYPE_MAP = {
    7: "SMALLINT",
    8: "INTEGER",
    10: "FLOAT",
    12: "DATE",
    14: "CHAR",
    16: "BIGINT/NUMERIC",
    27: "DOUBLE",
    35: "TIMESTAMP",
    37: "VARCHAR",
    261: "BLOB",
}

_CAMPO_OK = re.compile(r"^[A-Z][A-Z0-9_]*$")


def conectar(cfg: dict | None = None):
    c = cfg or carregar_conexao()
    return firebirdsql.connect(
        host=c["host"],
        port=int(c["port"]),
        database=c["database"],
        user=c["user"],
        password=c["password"],
        charset=c["charset"],
    )


def testar_conexao(cfg: dict | None = None) -> dict:
    conn = conectar(cfg)
    try:
        cur = conn.cursor()
        cur.execute("SELECT CURRENT_USER FROM RDB$DATABASE")
        (usuario,) = cur.fetchone()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM RDB$RELATIONS
            WHERE RDB$SYSTEM_FLAG = 0 AND RDB$VIEW_BLR IS NULL
            """
        )
        (tabelas,) = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM ESTOQUE")
        (estoque,) = cur.fetchone()
        return {
            "ok": True,
            "usuario": (usuario or "").strip(),
            "tabelas": tabelas,
            "estoque": estoque,
        }
    finally:
        conn.close()


def listar_campos_estoque() -> list[dict]:
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                TRIM(rf.RDB$FIELD_NAME),
                f.RDB$FIELD_TYPE,
                COALESCE(f.RDB$CHARACTER_LENGTH, f.RDB$FIELD_LENGTH),
                f.RDB$FIELD_SCALE,
                rf.RDB$NULL_FLAG
            FROM RDB$RELATION_FIELDS rf
            JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE
            WHERE TRIM(rf.RDB$RELATION_NAME) = 'ESTOQUE'
            ORDER BY rf.RDB$FIELD_POSITION
            """
        )
        campos = []
        for nome, ftype, length, scale, not_null in cur.fetchall():
            nome = nome.strip()
            if nome in CAMPOS_IGNORADOS:
                continue
            tipo = _TYPE_MAP.get(ftype, str(ftype))
            if scale and scale < 0:
                tipo = f"NUMERIC(scale={abs(scale)})"
            campos.append(
                {
                    "nome": nome,
                    "tipo": tipo,
                    "ftype": ftype,
                    "tamanho": length,
                    "obrigatorio": bool(not_null),
                }
            )
        return campos
    finally:
        conn.close()


def _nomes_campos_validos() -> set[str]:
    return {c["nome"] for c in listar_campos_estoque()}


def listar_valores_distintos(campo: str, limite: int = 200) -> list[str]:
    campo = (campo or "").strip().upper()
    if not _CAMPO_OK.match(campo):
        raise ValueError(f"Campo inválido: {campo}")
    if campo not in _nomes_campos_validos():
        raise ValueError(f"Campo não existe em ESTOQUE: {campo}")

    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT FIRST {int(limite)} {campo}
            FROM ESTOQUE
            WHERE {campo} IS NOT NULL
            GROUP BY {campo}
            ORDER BY 1
            """
        )
        valores: list[str] = []
        for (val,) in cur.fetchall():
            if val is None or isinstance(val, bytes):
                continue
            texto = str(val).strip() if isinstance(val, str) else str(val)
            if texto:
                valores.append(texto)
        return valores
    finally:
        conn.close()
