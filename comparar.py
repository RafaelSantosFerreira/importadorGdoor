from __future__ import annotations

import progresso
from csv_origem import ler_linhas_csv
from db import conectar
from mapeamento_store import carregar as carregar_mapeamento
from transform import (
    CAMPOS_ESTOQUE,
    CAMPOS_PRECO,
    fmt_num,
    montar_registro,
    num_eq,
)


def _buscar_estoque(cur, codigos: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    campos = ["CODIGO", "DESCRICAO", "BARRAS", *CAMPOS_PRECO, *CAMPOS_ESTOQUE]
    cols = ", ".join(campos)
    total = len(codigos)
    for i in range(0, total, 400):
        chunk = codigos[i : i + 400]
        ph = ",".join("?" * len(chunk))
        cur.execute(f"SELECT {cols} FROM ESTOQUE WHERE CODIGO IN ({ph})", chunk)
        for row in cur.fetchall():
            item = {}
            for idx, nome in enumerate(campos):
                val = row[idx]
                if isinstance(val, str):
                    val = val.strip()
                item[nome] = val
            out[item["CODIGO"]] = item
        progresso.update(
            etapa="consulta",
            atual=min(i + 400, total),
            total=total,
            mensagem=f"Lendo estoque do banco… {min(i + 400, total)}/{total}",
        )
    return out


def comparar_preco_estoque(limite_log: int = 500) -> dict:
    progresso.update(etapa="csv", mensagem="Lendo CSV…")
    cfg_map = carregar_mapeamento()
    mapeamento = cfg_map.get("mapeamento") or {}
    valores_padrao = cfg_map.get("valores_padrao") or {}

    if "CODIGO" not in mapeamento and "CODIGO" not in valores_padrao:
        raise ValueError("Configure o de-para do campo CODIGO.")

    rows = ler_linhas_csv(cfg_map.get("csv"))
    registros = []
    total_rows = len(rows)
    for idx, row in enumerate(rows, start=1):
        reg = montar_registro(row, mapeamento, valores_padrao)
        if reg:
            registros.append(reg)
        if idx % 500 == 0 or idx == total_rows:
            progresso.update(
                etapa="csv",
                atual=idx,
                total=total_rows,
                mensagem=f"Preparando comparação… {idx}/{total_rows}",
            )

    progresso.update(etapa="conexao", mensagem="Conectando no Firebird…")
    conn = conectar()
    try:
        cur = conn.cursor()
        atuais = _buscar_estoque(cur, [r["CODIGO"] for r in registros])
    finally:
        conn.close()

    log = []
    novos = 0
    iguais = 0
    dif_preco = 0
    dif_estoque = 0
    dif_ambos = 0
    total = len(registros)

    for i, reg in enumerate(registros, start=1):
        codigo = reg["CODIGO"]
        atual = atuais.get(codigo)
        if not atual:
            novos += 1
            if len(log) < limite_log:
                log.append(
                    {
                        "codigo": codigo,
                        "descricao": reg.get("DESCRICAO") or "",
                        "tipo": "NOVO",
                        "preco_csv": fmt_num(reg.get("PRECO_VENDA")),
                        "preco_banco": "",
                        "custo_csv": fmt_num(reg.get("PRECO_CUSTO")),
                        "custo_banco": "",
                        "qtd_csv": fmt_num(reg.get("QTD")),
                        "qtd_banco": "",
                        "detalhe": "Não existe no banco",
                    }
                )
        else:
            mudou_preco = False
            mudou_estoque = False
            detalhes = []

            for campo in CAMPOS_PRECO:
                if campo not in reg:
                    continue
                if not num_eq(reg.get(campo), atual.get(campo)):
                    mudou_preco = True
                    detalhes.append(
                        f"{campo}: banco={fmt_num(atual.get(campo))} -> csv={fmt_num(reg.get(campo))}"
                    )

            for campo in CAMPOS_ESTOQUE:
                if campo not in reg:
                    continue
                if not num_eq(reg.get(campo), atual.get(campo)):
                    mudou_estoque = True
                    detalhes.append(
                        f"{campo}: banco={fmt_num(atual.get(campo))} -> csv={fmt_num(reg.get(campo))}"
                    )

            if mudou_preco and mudou_estoque:
                dif_ambos += 1
                tipo = "PRECO+ESTOQUE"
            elif mudou_preco:
                dif_preco += 1
                tipo = "PRECO"
            elif mudou_estoque:
                dif_estoque += 1
                tipo = "ESTOQUE"
            else:
                iguais += 1
                tipo = None

            if tipo and len(log) < limite_log:
                log.append(
                    {
                        "codigo": codigo,
                        "descricao": (reg.get("DESCRICAO") or atual.get("DESCRICAO") or ""),
                        "tipo": tipo,
                        "preco_csv": fmt_num(reg.get("PRECO_VENDA")),
                        "preco_banco": fmt_num(atual.get("PRECO_VENDA")),
                        "custo_csv": fmt_num(reg.get("PRECO_CUSTO")),
                        "custo_banco": fmt_num(atual.get("PRECO_CUSTO")),
                        "qtd_csv": fmt_num(reg.get("QTD")),
                        "qtd_banco": fmt_num(atual.get("QTD")),
                        "detalhe": " | ".join(detalhes),
                    }
                )

        if i % 200 == 0 or i == total:
            progresso.update(
                etapa="comparacao",
                atual=i,
                total=total,
                mensagem=f"Comparando {i}/{total} | dif preço={dif_preco} estoque={dif_estoque}",
            )

    return {
        "total_csv": len(registros),
        "existentes": len(registros) - novos,
        "novos": novos,
        "iguais": iguais,
        "dif_preco": dif_preco,
        "dif_estoque": dif_estoque,
        "dif_ambos": dif_ambos,
        "log_truncado": len(log) >= limite_log,
        "log": log,
    }
