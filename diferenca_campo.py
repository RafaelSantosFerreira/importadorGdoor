"""Motor comum das telas que comparam um campo numérico do CSV com o ESTOQUE.

Casamento: ``cast(CODIGO as int) = cast(id_identificador as int)``, já que
CODIGO é VARCHAR(6) com zeros à esquerda (``004152``) e o CSV traz ``4152``.
Código que não é inteiro não casa com ninguém — o cast falharia no banco —, e
entra na contagem ``sem_codigo``.

Cada tela declara um :class:`Campo` dizendo qual coluna do ESTOQUE grava, qual
coluna do CSV é a origem e qual valor é perigoso demais para gravar
(``bloqueia``). O valor bloqueado aparece na lista marcado, para o usuário ver,
mas nunca vira UPDATE.

Operações, sobre a mesma análise:
- ``buscar(campo)``        -> só leitura, lista o que está diferente.
- ``aplicar(campo, ...)``  -> grava; numa única transação, qualquer erro
  (ou dry run) => ROLLBACK.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

import progresso
from csv_origem import ler_linhas_csv
from db import conectar
from mapeamento_store import carregar as carregar_mapeamento
from transform import fmt_num, para_numero

COLUNA_IDENTIFICADOR = "id_identificador"
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


@dataclass(frozen=True)
class Campo:
    destino: str  # coluna do ESTOQUE que recebe o valor
    coluna_padrao: str  # coluna do CSV quando o de-para não define
    modo: str  # identificador da operação, usado no progresso
    rotulo: str  # "preço" / "saldo", para as mensagens
    bloqueia: Callable[[Decimal, Decimal | None], bool]
    motivo: str  # badge mostrado no item bloqueado

    def coluna_csv(self, cfg: dict) -> str:
        return (cfg.get("mapeamento") or {}).get(self.destino) or self.coluna_padrao


def _carregar_banco(cur, destino: str) -> dict[int, tuple[str, Decimal | None, str]]:
    """cast(CODIGO as int) -> (CODIGO exato, valor atual do campo, DESCRICAO)."""
    cur.execute(f"SELECT CODIGO, {destino}, DESCRICAO FROM ESTOQUE")
    out: dict[int, tuple[str, Decimal | None, str]] = {}
    for codigo, valor, descricao in cur.fetchall():
        chave = como_int(codigo)
        if chave is not None:
            out[chave] = (codigo, valor, (descricao or "").strip())
    return out


def _analisar(cur, campo: Campo, rows: list[dict], coluna_csv: str) -> dict:
    """Percorre o CSV e separa o que está diferente do banco."""
    banco = _carregar_banco(cur, campo.destino)

    diferentes: list[dict] = []
    iguais = sem_codigo = sem_valor = nao_encontrados = duplicados = bloqueados = 0
    faltando: list[str] = []
    vistos: set[int] = set()
    total = len(rows)

    for i, row in enumerate(rows, start=1):
        bruto = (row.get(COLUNA_IDENTIFICADOR) or "").strip()
        chave = como_int(bruto)
        valor_csv = para_numero(row.get(coluna_csv))

        if chave is None:
            sem_codigo += 1
        elif chave in vistos:
            duplicados += 1
        elif chave not in banco:
            nao_encontrados += 1
            if len(faltando) < 200:
                faltando.append(bruto)
        elif valor_csv is None:
            sem_valor += 1
        else:
            codigo_db, atual, descricao = banco[chave]
            atual_dec = Decimal(str(atual)) if atual is not None else None
            if atual_dec is not None and atual_dec == valor_csv:
                iguais += 1
            else:
                bloqueado = campo.bloqueia(valor_csv, atual_dec)
                if bloqueado:
                    bloqueados += 1
                if len(diferentes) < LIMITE_ITENS:
                    diferentes.append(
                        {
                            "codigo": str(codigo_db).strip(),
                            "descricao": descricao,
                            "valor_banco": fmt_num(atual),
                            "valor_csv": fmt_num(valor_csv),
                            "bloqueado": bloqueado,
                            "motivo": campo.motivo if bloqueado else "",
                            "_codigo_db": codigo_db,
                            "_valor": valor_csv,
                        }
                    )

        if chave is not None:
            vistos.add(chave)

        if i % 500 == 0 or i == total:
            progresso.update(
                etapa="analise",
                atual=i,
                total=total,
                mensagem=f"Comparando {campo.rotulo} {i}/{total} | diferentes={len(diferentes)}",
            )

    return {
        "itens": diferentes,
        "iguais": iguais,
        "sem_codigo": sem_codigo,
        "sem_valor": sem_valor,
        "nao_encontrados": nao_encontrados,
        "nao_encontrados_amostra": faltando,
        "duplicados": duplicados,
        "bloqueados": bloqueados,
        "linhas_csv": total,
    }


def _preparar(campo: Campo) -> tuple[list[dict], str]:
    progresso.update(etapa="csv", mensagem="Lendo CSV…")
    cfg = carregar_mapeamento()
    coluna_csv = campo.coluna_csv(cfg)
    rows = ler_linhas_csv(cfg.get("csv"))
    if rows and COLUNA_IDENTIFICADOR not in rows[0]:
        raise ValueError(f"Coluna '{COLUNA_IDENTIFICADOR}' não existe no CSV.")
    if rows and coluna_csv not in rows[0]:
        raise ValueError(f"Coluna '{coluna_csv}' não existe no CSV.")
    return rows, coluna_csv


def _limpar(itens: list[dict]) -> list[dict]:
    return [{k: v for k, v in it.items() if not k.startswith("_")} for it in itens]


def _comum(campo: Campo, coluna_csv: str) -> dict:
    return {
        "ok": True,
        "modo": campo.modo,
        "campo_destino": campo.destino,
        "coluna_codigo": COLUNA_IDENTIFICADOR,
        "coluna_csv": coluna_csv,
    }


def buscar(campo: Campo) -> dict:
    """Só leitura: lista os produtos cujo campo difere do CSV."""
    rows, coluna_csv = _preparar(campo)

    progresso.update(etapa="conexao", mensagem=f"Lendo {campo.rotulo} do banco…")
    conn = conectar()
    try:
        dados = _analisar(conn.cursor(), campo, rows, coluna_csv)
    finally:
        conn.close()

    total_dif = len(dados["itens"])
    msg = (
        f"{total_dif} produto(s) com {campo.rotulo} diferente."
        if total_dif
        else f"Nenhuma diferença de {campo.rotulo}."
    )
    progresso.update(etapa="fim", mensagem=msg)
    return {
        **_comum(campo, coluna_csv),
        "diferentes": total_dif,
        "truncado": total_dif >= LIMITE_ITENS,
        "situacao": msg,
        **{k: v for k, v in dados.items() if k != "itens"},
        "itens": _limpar(dados["itens"]),
    }


def aplicar(campo: Campo, *, dry_run: bool = True) -> dict:
    """Grava no banco os valores do CSV que estão diferentes."""
    rows, coluna_csv = _preparar(campo)

    progresso.update(etapa="conexao", mensagem=f"Lendo {campo.rotulo} do banco…")
    conn = conectar()
    try:
        cur = conn.cursor()
        dados = _analisar(cur, campo, rows, coluna_csv)

        atualizados = pulados = erros = 0
        log: list[str] = []
        erros_log: list[str] = []
        acao = "Simulando" if dry_run else "Gravando"
        alvos = dados["itens"]
        total = len(alvos)

        for i, item in enumerate(alvos, start=1):
            if item["bloqueado"]:
                pulados += 1
                continue
            try:
                cur.execute(
                    f"UPDATE ESTOQUE SET {campo.destino} = ? WHERE CODIGO = ?",
                    (item["_valor"], item["_codigo_db"]),
                )
                atualizados += 1
                if len(log) < 300:
                    log.append(
                        f"{campo.destino} {item['codigo']}: "
                        f"{item['valor_banco'] or 'vazio'} -> {item['valor_csv']}"
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
                    mensagem=f"{acao} {campo.rotulo} {i}/{total} | alterados={atualizados} erros={erros}",
                )

        gravado = not dry_run and erros == 0
        if gravado:
            conn.commit()
            situacao = f"COMMIT: {atualizados} registro(s) gravado(s) em {campo.destino}."
        else:
            conn.rollback()
            situacao = (
                "ROLLBACK: simulação, nada gravado."
                if dry_run
                else f"ROLLBACK: {erros} erro(s), NADA foi gravado."
            )

        progresso.update(etapa="fim", atual=total, total=total, mensagem=situacao)
        return {
            **_comum(campo, coluna_csv),
            "modo": f"{campo.modo}_aplicar",
            "dry_run": dry_run,
            "gravado": gravado,
            "situacao": situacao,
            "diferentes": len(alvos),
            "truncado": len(alvos) >= LIMITE_ITENS,
            "atualizados": atualizados,
            "pulados": pulados,
            "erros": erros,
            **{k: v for k, v in dados.items() if k != "itens"},
            "itens": _limpar(alvos),
            "log": erros_log + log,
        }
    finally:
        conn.close()
