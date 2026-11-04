"""Diferenças de QTD entre o CSV e a tabela ESTOQUE.

Casamento e fluxo ficam em :mod:`diferenca_campo`; aqui só a definição do campo.

Grava em QTD, não em QTD_SALDO: no Firebird QTD_SALDO é coluna calculada
(``qtd - qtd_ideal``) e o UPDATE nela dá "attempted update of read-only
column". Mexendo em QTD, o banco recalcula QTD_SALDO e QTD_DISPONIVEL.

Salvaguarda: quantidade negativa no CSV aparece na busca marcada, mas NÃO é
gravada — saldo negativo costuma ser erro de exportação, não estoque real.
"""

from __future__ import annotations

from diferenca_campo import Campo, aplicar, buscar

QTD = Campo(
    destino="QTD",
    coluna_padrao="qtd_atual",
    modo="dif_saldo",
    rotulo="saldo",
    bloqueia=lambda csv, banco: csv < 0,
    motivo="negativo — não grava",
)


def buscar_diferencas_saldo() -> dict:
    return buscar(QTD)


def aplicar_diferencas_saldo(*, dry_run: bool = True) -> dict:
    return aplicar(QTD, dry_run=dry_run)
