from __future__ import annotations

import csv
from pathlib import Path

from conexao_store import carregar as carregar_conexao


def caminho_csv(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    return Path(carregar_conexao()["csv"])


def ler_cabecalho_e_amostra(
    path: str | Path | None = None,
    max_amostras: int = 3,
) -> dict:
    cfg = carregar_conexao()
    arquivo = caminho_csv(path)
    encoding = cfg.get("csv_encoding") or "latin-1"
    delimiter = cfg.get("csv_delimiter") or ";"

    if not arquivo.exists():
        raise FileNotFoundError(f"CSV não encontrado: {arquivo}")

    with arquivo.open("r", encoding=encoding, newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        headers = [h.strip() for h in next(reader)]
        amostras: list[list[str]] = []
        for i, row in enumerate(reader):
            if i >= max_amostras:
                break
            amostras.append(row)

    with arquivo.open("r", encoding=encoding, newline="") as f:
        total = sum(1 for _ in f) - 1

    colunas = []
    for i, nome in enumerate(headers):
        exemplos = []
        for row in amostras:
            if i < len(row) and row[i].strip():
                exemplos.append(row[i].strip()[:60])
        colunas.append({"indice": i, "nome": nome, "exemplos": exemplos[:3]})

    return {
        "arquivo": str(arquivo),
        "nome_arquivo": arquivo.name,
        "total_linhas": max(total, 0),
        "delimiter": delimiter,
        "encoding": encoding,
        "colunas": colunas,
    }


def ler_linhas_csv(path: str | Path | None = None) -> list[dict]:
    cfg = carregar_conexao()
    arquivo = caminho_csv(path)
    encoding = cfg.get("csv_encoding") or "latin-1"
    delimiter = cfg.get("csv_delimiter") or ";"
    with arquivo.open("r", encoding=encoding, newline="") as f:
        return list(csv.DictReader(f, delimiter=delimiter))
