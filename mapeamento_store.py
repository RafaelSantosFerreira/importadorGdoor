from __future__ import annotations

import json

from config import (
    CSV_PADRAO,
    MAPEAMENTO_PATH,
    MAPEAMENTO_SUGERIDO,
    VALORES_PADRAO_SUGERIDOS,
)
from conexao_store import carregar as carregar_conexao


def carregar() -> dict:
    csv_conexao = carregar_conexao().get("csv") or str(CSV_PADRAO)
    if MAPEAMENTO_PATH.exists():
        data = json.loads(MAPEAMENTO_PATH.read_text(encoding="utf-8"))
    else:
        data = {
            "csv": csv_conexao,
            "tabela_destino": "ESTOQUE",
            "mapeamento": dict(MAPEAMENTO_SUGERIDO),
            "valores_padrao": dict(VALORES_PADRAO_SUGERIDOS),
        }
    data.setdefault("csv", csv_conexao)
    # sempre prioriza o CSV da tela de conexão
    data["csv"] = csv_conexao
    data.setdefault("tabela_destino", "ESTOQUE")
    data.setdefault("mapeamento", {})
    data.setdefault("valores_padrao", {})
    return data


def salvar(payload: dict) -> dict:
    mapeamento = payload.get("mapeamento") or {}
    valores_padrao = payload.get("valores_padrao") or {}
    csv_conexao = carregar_conexao().get("csv") or str(CSV_PADRAO)

    limpo_map = {
        destino: str(origem).strip()
        for destino, origem in mapeamento.items()
        if origem is not None and str(origem).strip()
    }
    # padrão só entra se o destino NÃO estiver mapeado para coluna CSV
    limpo_padrao = {}
    for destino, valor in valores_padrao.items():
        if destino in limpo_map:
            continue
        if valor is None:
            continue
        texto = str(valor)
        # permite "0" e espaços intencionais; só ignora string vazia pura
        if texto == "":
            continue
        limpo_padrao[destino] = texto

    data = {
        "csv": payload.get("csv") or csv_conexao,
        "tabela_destino": payload.get("tabela_destino") or "ESTOQUE",
        "mapeamento": limpo_map,
        "valores_padrao": limpo_padrao,
    }
    MAPEAMENTO_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return data


def aplicar_sugestao(colunas_csv: list[str]) -> dict:
    set_csv = {c.lower(): c for c in colunas_csv}
    mapeamento = {}
    for destino, origem in MAPEAMENTO_SUGERIDO.items():
        key = origem.lower()
        if key in set_csv:
            mapeamento[destino] = set_csv[key]

    valores_padrao = {
        destino: valor
        for destino, valor in VALORES_PADRAO_SUGERIDOS.items()
        if destino not in mapeamento
    }
    return {"mapeamento": mapeamento, "valores_padrao": valores_padrao}
