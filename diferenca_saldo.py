"""Diferenças de QTD_SALDO entre o CSV e a tabela ESTOQUE.

Casamento e fluxo ficam em :mod:`diferenca_campo`; aqui só a definição do campo.

Salvaguarda: quantidade negativa no CSV aparece na busca marcada, mas NÃO é
gravada — saldo negativo costuma ser erro de exportação, não estoque real.
"""

from __future__ import annotations

from diferenca_campo import Campo, aplicar, buscar

QTD_SALDO = Campo(
    destino="QTD_SALDO",
    coluna_padrao="qtd_atual",
    modo="dif_saldo",
    rotulo="saldo",
    bloqueia=lambda csv, banco: csv < 0,
    motivo="negativo — não grava",
)


def buscar_diferencas_saldo() -> dict:
    return buscar(QTD_SALDO)


def aplicar_diferencas_saldo(*, dry_run: bool = True) -> dict:
    return aplicar(QTD_SALDO, dry_run=dry_run)
