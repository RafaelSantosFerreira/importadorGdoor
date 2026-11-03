"""Analisa o CSV de itens e propõe mapeamento para ESTOQUE."""

import csv
from collections import Counter
from pathlib import Path

CSV_PATH = Path(r"C:\Users\rscholant\Downloads\itens.csv")

# Hipótese de colunas (CSV sem cabeçalho, separador ;)
NOMES = [
    "codigo",
    "barras",
    "descricao",
    "descricao2",
    "und",
    "und_compra",
    "preco_custo",
    "custo_medio",
    "preco_venda",
    "preco_venda2",
    "campo10",
    "campo11",
    "ncm",
    "cest",
    "flag14",
    "flag15",
    "flag16",
    "campo17",
    "campo18",
    "campo19",
    "ncm_desc",
]


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    print(f"Arquivo: {CSV_PATH}")
    print(f"Linhas: {len(rows)}")
    lens = Counter(len(r) for r in rows)
    print(f"Qtd colunas por linha: {dict(lens)}")

    print("\n=== Amostra (3 linhas) ===")
    for row in rows[:3]:
        for i, v in enumerate(row):
            nome = NOMES[i] if i < len(NOMES) else f"col{i}"
            print(f"  [{i:02d}] {nome}: {v!r}")
        print("---")

    codigos = [r[0].strip() for r in rows if r]
    print(f"\nCódigo min/max len: {min(map(len, codigos))}/{max(map(len, codigos))}")
    print(f"Códigos únicos: {len(set(codigos))}")


if __name__ == "__main__":
    main()
