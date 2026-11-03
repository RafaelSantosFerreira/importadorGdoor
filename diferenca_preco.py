"""Diferenças de PRECO_VENDA entre o CSV e a tabela ESTOQUE.

Casamento e fluxo ficam em :mod:`diferenca_campo`; aqui só a definição do campo.

Salvaguarda: preço 0 no CSV contra preço maior que zero no banco aparece na
busca marcado, mas NÃO é gravado — "preço zero não zera o banco", como no
resto do app.
"""

from __future__ import annotations

from decimal import Decimal

from diferenca_campo import COLUNA_IDENTIFICADOR, Campo, aplicar, buscar, como_int  # noqa: F401

PRECO_VENDA = Campo(
    destino="PRECO_VENDA",
    coluna_padrao="prc_venda",
    modo="dif_preco",
    rotulo="preço",
    bloqueia=lambda csv, banco: csv == 0 and (banco or Decimal(0)) > 0,
    motivo="zeraria — não grava",
)


def buscar_diferencas_preco() -> dict:
    return buscar(PRECO_VENDA)


def aplicar_diferencas_preco(*, dry_run: bool = True) -> dict:
    return aplicar(PRECO_VENDA, dry_run=dry_run)
