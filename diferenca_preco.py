"""Diferenças de PRECO_VENDA entre o CSV e a tabela ESTOQUE.

Casamento: ``cast(CODIGO as int) = cast(id_identificador as int)``, já que
CODIGO é VARCHAR(6) com zeros à esquerda (``004152``) e o CSV traz ``4152``.
Código que não é inteiro não casa com ninguém — o cast falharia no banco —, e
entra na contagem ``sem_codigo``.

Condição de diferença: ``PRECO_VENDA <> prc_venda``.

Duas operações, sobre a mesma análise:
- ``buscar_diferencas_preco()``  -> só leitura, lista o que está diferente.
- ``aplicar_diferencas_preco()`` -> grava PRECO_VENDA; numa única transação,
  qualquer erro (ou dry run) => ROLLBACK.

Salvaguarda: uma linha com preço 0 no CSV contra preço > 0 no banco aparece na
busca marcada como ``zeraria``, mas NÃO é gravada — é o mesmo princípio do resto
do app ("preço zero não zera o banco").
"""

from __future__ import annotations

from decimal import Decimal

import progresso
from csv_origem import ler_linhas_csv
from db import conectar
from mapeamento_store import carregar as carregar_mapeamento
from transform import fmt_num, para_numero

COLUNA_IDENTIFICADOR = "id_identificador"
COLUNA_PRECO_PADRAO = "prc_venda"
LIMITE_ITENS = 2000


def como_int(valor) -> int | None:
    """Equivalente a ``cast(valor as int)``; None quando não dá para converter."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        return None


def _coluna_preco(cfg: dict) -> str:
    return (cfg.get("mapeamento") or {}).get("PRECO_VENDA") or COLUNA_PRECO_PADRAO


def _carregar_banco(cur) -> dict[int, tuple[str, Decimal | None, str]]:
    """cast(CODIGO as int) -> (CODIGO exato, PRECO_VENDA atual, DESCRICAO)."""
    cur.execute("SELECT CODIGO, PRECO_VENDA, DESCRICAO FROM ESTOQUE")
    out: dict[int, tuple[str, Decimal | None, str]] = {}
    for codigo, preco, descricao in cur.fetchall():
        chave = como_int(codigo)
        if chave is not None:
            out[chave] = (codigo, preco, (descricao or "").strip())
    return out


def _analisar(cur, rows: list[dict], coluna_preco: str) -> dict:
    """Percorre o CSV e separa o que está diferente do banco."""
    banco = _carregar_banco(cur)

    diferentes: list[dict] = []
    iguais = sem_codigo = sem_preco = nao_encontrados = duplicados = zerariam = 0
    faltando: list[str] = []
    vistos: set[int] = set()
    total = len(rows)

    for i, row in enumerate(rows, start=1):
        bruto = (row.get(COLUNA_IDENTIFICADOR) or "").strip()
        chave = como_int(bruto)
        preco_csv = para_numero(row.get(coluna_preco))

        if chave is None:
            sem_codigo += 1
        elif chave in vistos:
            duplicados += 1
        elif chave not in banco:
            nao_encontrados += 1
            if len(faltando) < 200:
                faltando.append(bruto)
        elif preco_csv is None:
            sem_preco += 1
        else:
            codigo_db, atual, descricao = banco[chave]
            atual_dec = Decimal(str(atual)) if atual is not None else None
            if atual_dec is not None and atual_dec == preco_csv:
                iguais += 1
            else:
                zeraria = preco_csv == 0 and (atual_dec or Decimal(0)) > 0
                if zeraria:
                    zerariam += 1
                if len(diferentes) < LIMITE_ITENS:
                    diferentes.append(
                        {
                            "codigo": str(codigo_db).strip(),
                            "descricao": descricao,
                            "preco_banco": fmt_num(atual),
                            "preco_csv": fmt_num(preco_csv),
                            "zeraria": zeraria,
                            "_codigo_db": codigo_db,
                            "_preco": preco_csv,
                        }
                    )

        if chave is not None:
            vistos.add(chave)

        if i % 500 == 0 or i == total:
            progresso.update(
                etapa="diferencas",
                atual=i,
                total=total,
                mensagem=f"Comparando preços {i}/{total} | diferentes={len(diferentes)}",
            )

    return {
        "itens": diferentes,
        "iguais": iguais,
        "sem_codigo": sem_codigo,
        "sem_preco": sem_preco,
        "nao_encontrados": nao_encontrados,
        "nao_encontrados_amostra": faltando,
        "duplicados": duplicados,
        "zerariam": zerariam,
        "linhas_csv": total,
    }


def _preparar() -> tuple[list[dict], str]:
    progresso.update(etapa="csv", mensagem="Lendo CSV…")
    cfg = carregar_mapeamento()
    coluna_preco = _coluna_preco(cfg)
    rows = ler_linhas_csv(cfg.get("csv"))
    if rows and COLUNA_IDENTIFICADOR not in rows[0]:
        raise ValueError(f"Coluna '{COLUNA_IDENTIFICADOR}' não existe no CSV.")
    if rows and coluna_preco not in rows[0]:
        raise ValueError(f"Coluna de preço '{coluna_preco}' não existe no CSV.")
    return rows, coluna_preco


def _limpar(itens: list[dict]) -> list[dict]:
    return [{k: v for k, v in it.items() if not k.startswith("_")} for it in itens]


def buscar_diferencas_preco() -> dict:
    """Só leitura: lista os produtos cujo PRECO_VENDA difere do CSV."""
    rows, coluna_preco = _preparar()

    progresso.update(etapa="conexao", mensagem="Lendo preços do banco…")
    conn = conectar()
    try:
        dados = _analisar(conn.cursor(), rows, coluna_preco)
    finally:
        conn.close()

    total_dif = len(dados["itens"])
    msg = (
        f"{total_dif} produto(s) com preço diferente."
        if total_dif
        else "Nenhuma diferença de preço."
    )
    progresso.update(etapa="fim", mensagem=msg)
    return {
        "ok": True,
        "modo": "dif_preco",
        "coluna_codigo": COLUNA_IDENTIFICADOR,
        "coluna_preco": coluna_preco,
        "diferentes": total_dif,
        "truncado": total_dif >= LIMITE_ITENS,
        "situacao": msg,
        **{k: v for k, v in dados.items() if k != "itens"},
        "itens": _limpar(dados["itens"]),
    }


def aplicar_diferencas_preco(*, dry_run: bool = True) -> dict:
    """Grava PRECO_VENDA do CSV nos produtos que estão diferentes."""
    rows, coluna_preco = _preparar()

    progresso.update(etapa="conexao", mensagem="Lendo preços do banco…")
    conn = conectar()
    try:
        cur = conn.cursor()
        dados = _analisar(cur, rows, coluna_preco)

        atualizados = pulados_zero = erros = 0
        log: list[str] = []
        erros_log: list[str] = []
        acao = "Simulando" if dry_run else "Gravando"
        alvos = dados["itens"]
        total = len(alvos)

        for i, item in enumerate(alvos, start=1):
            if item["zeraria"]:
                pulados_zero += 1
                continue
            try:
                cur.execute(
                    "UPDATE ESTOQUE SET PRECO_VENDA = ? WHERE CODIGO = ?",
                    (item["_preco"], item["_codigo_db"]),
                )
                atualizados += 1
                if len(log) < 300:
                    log.append(
                        f"PRECO {item['codigo']}: "
                        f"{item['preco_banco'] or 'vazio'} -> {item['preco_csv']}"
                    )
            except Exception as e:
                erros += 1
                if len(erros_log) < 300:
                    erros_log.append(f"ERRO {item['codigo']}: {e or type(e).__name__}")

            if i % 200 == 0 or i == total:
                progresso.update(
                    etapa="gravacao",
                    atual=i,
                    total=total,
                    mensagem=f"{acao} preços {i}/{total} | alterados={atualizados} erros={erros}",
                )

        gravado = not dry_run and erros == 0
        if gravado:
            conn.commit()
            situacao = f"COMMIT: {atualizados} preço(s) gravado(s)."
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
            "modo": "dif_preco_aplicar",
            "dry_run": dry_run,
            "gravado": gravado,
            "situacao": situacao,
            "coluna_codigo": COLUNA_IDENTIFICADOR,
            "coluna_preco": coluna_preco,
            "diferentes": len(alvos),
            "truncado": len(alvos) >= LIMITE_ITENS,
            "atualizados": atualizados,
            "pulados_zero": pulados_zero,
            "erros": erros,
            **{k: v for k, v in dados.items() if k != "itens"},
            "itens": _limpar(alvos),
            "log": erros_log + log,
        }
    finally:
        conn.close()
