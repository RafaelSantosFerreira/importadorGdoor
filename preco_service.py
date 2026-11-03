"""Atualiza somente o PRECO_VENDA de produtos já existentes.

Casamento: ESTOQUE.CODIGO  <->  coluna `id_estoque` do CSV, comparando pelo
valor (``4152`` == ``004152``), sem depender de zeros à esquerda.

Regras:
- Nunca insere produto e não altera nenhum outro campo.
- Preço vazio, inválido ou zero no CSV é ignorado (não zera o banco).
- Preço igual ao do banco não gera UPDATE.
- Uma única transação: simulação ou qualquer erro => ROLLBACK.
"""

from __future__ import annotations

from decimal import Decimal

import progresso
from csv_origem import ler_linhas_csv
from db import conectar
from mapeamento_store import carregar as carregar_mapeamento
from transform import fmt_num, para_numero

COLUNA_CODIGO = "id_estoque"
COLUNA_PRECO_PADRAO = "prc_venda"


def normalizar_codigo(valor) -> str | None:
    if valor is None:
        return None
    v = str(valor).strip()
    if not v:
        return None
    if v.isdigit():
        return v.lstrip("0") or "0"
    return v.upper()


def _carregar_banco(cur) -> dict[str, tuple[str, Decimal | None]]:
    """codigo_normalizado -> (CODIGO exato no banco, PRECO_VENDA atual)."""
    cur.execute("SELECT CODIGO, PRECO_VENDA FROM ESTOQUE")
    out: dict[str, tuple[str, Decimal | None]] = {}
    for codigo, preco in cur.fetchall():
        chave = normalizar_codigo(codigo)
        if chave is not None:
            out[chave] = (codigo, preco)
    return out


def atualizar_somente_preco(*, dry_run: bool = True) -> dict:
    progresso.update(etapa="csv", mensagem="Lendo CSV…")
    cfg = carregar_mapeamento()
    coluna_preco = (cfg.get("mapeamento") or {}).get("PRECO_VENDA") or COLUNA_PRECO_PADRAO

    rows = ler_linhas_csv(cfg.get("csv"))
    if rows and COLUNA_CODIGO not in rows[0]:
        raise ValueError(f"Coluna '{COLUNA_CODIGO}' não existe no CSV.")
    if rows and coluna_preco not in rows[0]:
        raise ValueError(f"Coluna de preço '{coluna_preco}' não existe no CSV.")

    progresso.update(etapa="conexao", mensagem="Lendo códigos e preços do banco…")
    conn = conectar()
    try:
        cur = conn.cursor()
        banco = _carregar_banco(cur)

        atualizados = iguais = sem_preco = nao_encontrados = duplicados = erros = 0
        log: list[str] = []
        erros_log: list[str] = []
        faltando: list[str] = []
        vistos: set[str] = set()
        total = len(rows)
        acao = "Simulando" if dry_run else "Gravando"

        for i, row in enumerate(rows, start=1):
            bruto = (row.get(COLUNA_CODIGO) or "").strip()
            chave = normalizar_codigo(bruto)
            preco = para_numero(row.get(coluna_preco))
            try:
                if chave is None:
                    sem_preco += 1
                elif chave in vistos:
                    duplicados += 1
                elif preco is None or preco <= 0:
                    sem_preco += 1
                elif chave not in banco:
                    nao_encontrados += 1
                    if len(faltando) < 200:
                        faltando.append(bruto)
                else:
                    codigo_db, atual = banco[chave]
                    if atual is not None and Decimal(str(atual)) == preco:
                        iguais += 1
                    else:
                        cur.execute(
                            "UPDATE ESTOQUE SET PRECO_VENDA = ? WHERE CODIGO = ?",
                            (preco, codigo_db),
                        )
                        atualizados += 1
                        if len(log) < 300:
                            log.append(
                                f"PRECO {str(codigo_db).strip()}: "
                                f"{fmt_num(atual) or 'vazio'} -> {fmt_num(preco)}"
                            )
                if chave is not None:
                    vistos.add(chave)
            except Exception as e:
                erros += 1
                if len(erros_log) < 300:
                    erros_log.append(f"ERRO {bruto}: {e}")

            if i % 200 == 0 or i == total:
                progresso.update(
                    etapa="preco",
                    atual=i,
                    total=total,
                    mensagem=f"{acao} preços {i}/{total} | alterados={atualizados} erros={erros}",
                )

        gravado = not dry_run and erros == 0
        if gravado:
            conn.commit()
            situacao = "COMMIT: preços gravados."
        else:
            conn.rollback()
            situacao = (
                "ROLLBACK: simulação, nada gravado."
                if dry_run
                else f"ROLLBACK: {erros} erro(s), NADA foi gravado."
            )

        progresso.update(etapa="fim", atual=total, total=total, mensagem=situacao)
        return {
            "ok": True,
            "modo": "preco",
            "dry_run": dry_run,
            "gravado": gravado,
            "situacao": situacao,
            "coluna_codigo": COLUNA_CODIGO,
            "coluna_preco": coluna_preco,
            "linhas_csv": total,
            "atualizados": atualizados,
            "iguais": iguais,
            "sem_preco": sem_preco,
            "nao_encontrados": nao_encontrados,
            "duplicados": duplicados,
            "erros": erros,
            "nao_encontrados_amostra": faltando,
            "log": erros_log + log,
        }
    finally:
        conn.close()
