"""Produtos que existem no CSV e não existem na tabela ESTOQUE.

O CSV é a referência: percorre as linhas do arquivo e lista as que não têm
correspondente no banco, casando por
``cast(CODIGO as int) = cast(id_identificador as int)``.

Só leitura — nada é gravado. Diferente do tile "Novos" da comparação, a lista
não divide espaço com as diferenças de preço, então todos os faltantes
aparecem.
"""

from __future__ import annotations

import progresso
from csv_origem import ler_linhas_csv
from db import conectar
from diferenca_preco import COLUNA_IDENTIFICADOR, como_int
from mapeamento_store import carregar as carregar_mapeamento

LIMITE_ITENS = 5000

# Campo do ESTOQUE -> coluna usada quando o de-para não define nada.
COLUNAS_EXIBIDAS = {
    "DESCRICAO": "descricao",
    "PRECO_VENDA": "prc_venda",
    "PRECO_CUSTO": "prc_custo",
    "QTD": "qtd_atual",
    "BARRAS": "cod_barra",
}


def _colunas(cfg: dict) -> dict[str, str]:
    mapeamento = cfg.get("mapeamento") or {}
    return {campo: mapeamento.get(campo) or padrao for campo, padrao in COLUNAS_EXIBIDAS.items()}


def _codigos_do_banco(cur) -> set[int]:
    cur.execute("SELECT CODIGO FROM ESTOQUE")
    codigos = {como_int(codigo) for (codigo,) in cur.fetchall()}
    codigos.discard(None)
    return codigos


def buscar_faltantes() -> dict:
    progresso.update(etapa="csv", mensagem="Lendo CSV…")
    cfg = carregar_mapeamento()
    rows = ler_linhas_csv(cfg.get("csv"))
    if rows and COLUNA_IDENTIFICADOR not in rows[0]:
        raise ValueError(f"Coluna '{COLUNA_IDENTIFICADOR}' não existe no CSV.")
    col = _colunas(cfg)

    progresso.update(etapa="conexao", mensagem="Lendo códigos do banco…")
    conn = conectar()
    try:
        no_banco = _codigos_do_banco(conn.cursor())
    finally:
        conn.close()

    itens: list[dict] = []
    existentes = sem_codigo = duplicados = 0
    vistos: set[int] = set()
    total = len(rows)

    def texto(row, campo):
        return (row.get(col[campo]) or "").strip()

    for i, row in enumerate(rows, start=1):
        bruto = (row.get(COLUNA_IDENTIFICADOR) or "").strip()
        chave = como_int(bruto)
        if chave is None:
            sem_codigo += 1
        elif chave in vistos:
            duplicados += 1
        elif chave in no_banco:
            existentes += 1
        else:
            if len(itens) < LIMITE_ITENS:
                itens.append(
                    {
                        "codigo": bruto,
                        "descricao": texto(row, "DESCRICAO"),
                        "barras": texto(row, "BARRAS"),
                        "preco_venda": texto(row, "PRECO_VENDA"),
                        "preco_custo": texto(row, "PRECO_CUSTO"),
                        "qtd": texto(row, "QTD"),
                        "linha": i + 1,  # +1 por causa do cabeçalho
                    }
                )
        if chave is not None:
            vistos.add(chave)

        if i % 500 == 0 or i == total:
            progresso.update(
                etapa="faltantes",
                atual=i,
                total=total,
                mensagem=f"Conferindo {i}/{total} | faltando={len(itens)}",
            )

    faltando = len(itens)
    msg = (
        f"{faltando} produto(s) do CSV não existem no banco."
        if faltando
        else "Todos os códigos do CSV já existem no banco."
    )
    progresso.update(etapa="fim", atual=total, total=total, mensagem=msg)
    return {
        "ok": True,
        "modo": "faltantes",
        "coluna_codigo": COLUNA_IDENTIFICADOR,
        "linhas_csv": total,
        "existentes": existentes,
        "faltando": faltando,
        "sem_codigo": sem_codigo,
        "duplicados": duplicados,
        "codigos_no_banco": len(no_banco),
        "truncado": faltando >= LIMITE_ITENS,
        "situacao": msg,
        "itens": itens,
    }
