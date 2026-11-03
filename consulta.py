"""Consulta de leitura ao banco: busca no ESTOQUE e SELECT livre.

Nada aqui grava. Toda consulta roda e termina em ROLLBACK, e o SQL livre só
aceita SELECT/WITH, num único comando. Não é uma barreira de segurança contra
quem tem a senha do banco — é uma trava contra o acidente de digitar um
UPDATE sem WHERE numa caixa de texto.
"""

from __future__ import annotations

import re

from db import conectar

LIMITE_PADRAO = 200
LIMITE_MAXIMO = 2000

# Colunas mostradas na busca rápida, na ordem.
COLUNAS_BUSCA = (
    "CODIGO",
    "DESCRICAO",
    "BARRAS",
    "PRECO_VENDA",
    "PRECO_CUSTO",
    "QTD",
    "QTD_SALDO",
    "UNIDADE",
    "SITUACAO",
)

_COMENTARIOS = re.compile(r"(--[^\n]*)|(/\*.*?\*/)", re.S)
_PROIBIDO = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|GRANT|REVOKE|RECREATE|"
    r"EXECUTE|COMMIT|ROLLBACK|SET\s+TRANSACTION)\b",
    re.I,
)


def _limite(valor, padrao: int = LIMITE_PADRAO) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return padrao
    return max(1, min(n, LIMITE_MAXIMO))


def _colunas_existentes(cur) -> list[str]:
    cur.execute(
        "SELECT TRIM(RDB$FIELD_NAME) FROM RDB$RELATION_FIELDS "
        "WHERE TRIM(RDB$RELATION_NAME) = 'ESTOQUE'"
    )
    return {nome.strip() for (nome,) in cur.fetchall()}


def _texto(valor):
    if valor is None:
        return None
    if isinstance(valor, bytes):
        return "<blob>"
    if isinstance(valor, str):
        return valor.strip()
    return str(valor)


def buscar_estoque(termo: str = "", limite=None) -> dict:
    """Busca por código, código de barras ou trecho da descrição."""
    termo = (termo or "").strip()
    n = _limite(limite)

    conn = conectar()
    try:
        cur = conn.cursor()
        existentes = _colunas_existentes(cur)
        colunas = [c for c in COLUNAS_BUSCA if c in existentes]
        lista = ", ".join(colunas)

        if not termo:
            sql = f"SELECT FIRST {n} {lista} FROM ESTOQUE ORDER BY CODIGO"
            params: tuple = ()
        else:
            # O CAST evita que o Firebird tipe o parâmetro pelo tamanho da
            # coluna: sem ele, um termo maior que CODIGO (VARCHAR(6)) quebra
            # com "string right truncation".
            como = f"%{termo.upper()}%"
            condicoes = [
                "UPPER(CAST(DESCRICAO AS VARCHAR(200))) LIKE ?",
                "CAST(CODIGO AS VARCHAR(200)) LIKE ?",
            ]
            params = (como, f"%{termo}%")
            if "BARRAS" in existentes:
                condicoes.append("CAST(BARRAS AS VARCHAR(200)) LIKE ?")
                params = params + (f"%{termo}%",)
            # Código digitado sem zeros à esquerda ainda acha o produto.
            # Até 9 dígitos para não estourar INTEGER com um EAN de 13.
            if termo.isdigit() and len(termo) <= 9:
                condicoes.append("CAST(CODIGO AS INTEGER) = ?")
                params = params + (int(termo),)
            sql = (
                f"SELECT FIRST {n} {lista} FROM ESTOQUE "
                f"WHERE {' OR '.join(condicoes)} ORDER BY CODIGO"
            )

        cur.execute(sql, params) if params else cur.execute(sql)
        linhas = [[_texto(v) for v in linha] for linha in cur.fetchall()]
        conn.rollback()
    finally:
        conn.close()

    return {
        "ok": True,
        "termo": termo,
        "colunas": colunas,
        "linhas": linhas,
        "total": len(linhas),
        "limite": n,
        "truncado": len(linhas) >= n,
        "sql": sql,
    }


def validar_select(sql: str) -> str:
    """Devolve o SQL limpo, ou levanta ValueError explicando a recusa."""
    bruto = (sql or "").strip()
    if not bruto:
        raise ValueError("Escreva uma consulta.")

    # tira comentários antes de olhar o conteúdo, para não esconder comando
    limpo = _COMENTARIOS.sub(" ", bruto).strip()
    if not limpo:
        raise ValueError("A consulta só tem comentários.")

    sem_ponto = limpo.rstrip().rstrip(";").strip()
    if ";" in sem_ponto:
        raise ValueError("Mande um comando por vez: há ';' no meio da consulta.")

    if not re.match(r"^(SELECT|WITH)\b", sem_ponto, re.I):
        raise ValueError("Só SELECT (ou WITH) é aceito aqui.")

    achado = _PROIBIDO.search(sem_ponto)
    if achado:
        raise ValueError(f"Esta tela é só de leitura e '{achado.group(1).upper()}' não é permitido.")

    return sem_ponto


def executar_select(sql: str, limite=None) -> dict:
    """Roda um SELECT e desfaz a transação; nada é gravado."""
    consulta = validar_select(sql)
    n = _limite(limite)

    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(consulta)
        colunas = [d[0].strip() if isinstance(d[0], str) else str(d[0]) for d in cur.description]
        linhas = []
        for linha in cur.fetchall():
            linhas.append([_texto(v) for v in linha])
            if len(linhas) >= n:
                break
        conn.rollback()
    finally:
        conn.close()

    return {
        "ok": True,
        "colunas": colunas,
        "linhas": linhas,
        "total": len(linhas),
        "limite": n,
        "truncado": len(linhas) >= n,
        "sql": consulta,
    }
