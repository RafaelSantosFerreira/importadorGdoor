"""Ajuste do saldo de UM produto, direto na tela de Consulta.

O saldo gravável do ESTOQUE é ``QTD``. ``QTD_SALDO`` (``qtd - qtd_ideal``) e
``QTD_DISPONIVEL`` (``qtd - qtd_reservada``) são colunas calculadas: o banco
recusa UPDATE nelas e as recalcula sozinho quando ``QTD`` muda.

O valor informado é uma atribuição, não uma soma: o saldo passa a ser aquele,
qualquer que fosse o anterior.

Travas, porque esta tela grava em produção:
- o produto precisa existir (casa ``cast(CODIGO as int)``, como o resto do app);
- saldo negativo é recusado, igual ao card de diferenças de saldo;
- o UPDATE é por ``CODIGO`` exato e só é confirmado se afetar 1 linha.
  Qualquer outro número de linhas, ou qualquer erro, termina em ROLLBACK.
"""

from __future__ import annotations

from decimal import Decimal

from db import conectar
from transform import fmt_num, para_numero

CAMPO = "QTD"
CALCULADAS = ("QTD_SALDO", "QTD_DISPONIVEL")


def _ler(cur, codigo: str) -> dict | None:
    cur.execute(
        f"SELECT CODIGO, DESCRICAO, {CAMPO}, {', '.join(CALCULADAS)}, QTD_IDEAL, QTD_RESERVADA "
        "FROM ESTOQUE WHERE CODIGO = ?",
        (codigo,),
    )
    linha = cur.fetchone()
    if not linha:
        return None
    cod, desc, qtd, saldo, disp, ideal, reservada = linha
    return {
        "codigo": str(cod).strip(),
        "descricao": (desc or "").strip(),
        "qtd": fmt_num(qtd),
        "qtd_saldo": fmt_num(saldo),
        "qtd_disponivel": fmt_num(disp),
        "qtd_ideal": fmt_num(ideal),
        "qtd_reservada": fmt_num(reservada),
    }


def _achar_codigo(cur, termo: str) -> str:
    """'4152' ou '004152' -> o CODIGO exato do banco. Levanta se não achar."""
    termo = (termo or "").strip()
    if not termo:
        raise ValueError("Informe o código do produto.")

    cur.execute("SELECT CODIGO FROM ESTOQUE WHERE CODIGO = ?", (termo,))
    achado = cur.fetchone()
    if achado:
        return str(achado[0]).strip()

    if termo.isdigit() and len(termo) <= 9:
        cur.execute("SELECT CODIGO FROM ESTOQUE WHERE CAST(CODIGO AS INTEGER) = ?", (int(termo),))
        linhas = cur.fetchall()
        if len(linhas) > 1:
            raise ValueError(f"'{termo}' casa com {len(linhas)} produtos. Use o código completo.")
        if linhas:
            return str(linhas[0][0]).strip()

    raise ValueError(f"Produto '{termo}' não existe no ESTOQUE.")


def consultar(codigo: str) -> dict:
    """Só leitura: o saldo de hoje do produto."""
    conn = conectar()
    try:
        cur = conn.cursor()
        produto = _ler(cur, _achar_codigo(cur, codigo))
        conn.rollback()
    finally:
        conn.close()
    return {"ok": True, "produto": produto, "campo": CAMPO}


def ajustar(codigo: str, valor) -> dict:
    """Deixa o saldo do produto igual a ``valor``. COMMIT só com 1 linha afetada."""
    novo = para_numero(valor)
    if novo is None:
        raise ValueError(f"Saldo inválido: {valor!r}.")
    if novo < 0:
        raise ValueError("Saldo negativo não é gravado.")

    conn = conectar()
    try:
        cur = conn.cursor()
        exato = _achar_codigo(cur, codigo)
        antes = _ler(cur, exato)

        cur.execute(f"UPDATE ESTOQUE SET {CAMPO} = ? WHERE CODIGO = ?", (novo, exato))
        afetadas = getattr(cur, "rowcount", -1)
        if afetadas != 1:
            conn.rollback()
            raise ValueError(f"ROLLBACK: o UPDATE afetaria {afetadas} linha(s), e não 1.")

        depois = _ler(cur, exato)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "ok": True,
        "gravado": True,
        "campo": CAMPO,
        "antes": antes,
        "depois": depois,
        "situacao": (
            f"COMMIT: {exato} {CAMPO} {antes['qtd'] or '0'} -> {depois['qtd']} "
            f"(QTD_SALDO {depois['qtd_saldo']})."
        ),
    }
