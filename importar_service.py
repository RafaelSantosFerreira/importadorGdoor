from __future__ import annotations

from datetime import date

import progresso
from csv_origem import ler_linhas_csv
from db import conectar
from mapeamento_store import carregar as carregar_mapeamento
from transform import CAMPOS_ESTOQUE, CAMPOS_PRECO, montar_registro

# Nunca mexer nesses campos em produtos que já existem no banco.
CAMPOS_NUNCA_ATUALIZAR = {"CODIGO", "DATA_CADASTRO"}


def _existentes(cur, codigos: list[str]) -> set[str]:
    achados: set[str] = set()
    total = len(codigos)
    for i in range(0, total, 500):
        chunk = codigos[i : i + 500]
        ph = ",".join("?" * len(chunk))
        cur.execute(f"SELECT CODIGO FROM ESTOQUE WHERE CODIGO IN ({ph})", chunk)
        for (cod,) in cur.fetchall():
            achados.add(cod.strip() if isinstance(cod, str) else str(cod).strip())
        progresso.update(
            etapa="consulta",
            atual=min(i + 500, total),
            total=total,
            mensagem=f"Consultando códigos existentes no banco… {min(i + 500, total)}/{total}",
        )
    return achados


def campos_para_update(
    mapeamento: dict[str, str],
    *,
    atualizar_preco: bool,
    atualizar_estoque: bool,
    atualizar_cadastro: bool,
) -> list[str]:
    """Campos que podem ser alterados em produtos existentes.

    Só entram campos que vêm de coluna do CSV (valores padrão servem apenas
    para produtos novos), e nunca CODIGO / DATA_CADASTRO.
    """
    campos = []
    for c in mapeamento:
        if c in CAMPOS_NUNCA_ATUALIZAR:
            continue
        if c in CAMPOS_PRECO:
            if atualizar_preco:
                campos.append(c)
        elif c in CAMPOS_ESTOQUE:
            if atualizar_estoque:
                campos.append(c)
        elif atualizar_cadastro:
            campos.append(c)
    return campos


def importar(
    *,
    atualizar_preco: bool = True,
    atualizar_estoque: bool = True,
    atualizar_cadastro: bool = False,
    inserir_novos: bool = True,
    dry_run: bool = True,
) -> dict:
    """Importa o CSV para ESTOQUE numa única transação.

    - Os comandos SQL são sempre executados (inclusive na simulação), para que
      constraints e triggers do banco apareçam como erro.
    - Simulação, ou qualquer erro, termina em ROLLBACK: nada é gravado.
    - Só faz COMMIT quando não é simulação e não houve nenhum erro.
    - Em UPDATE, valores vazios do CSV são ignorados (não apagam dado do banco).
    """
    progresso.update(etapa="csv", mensagem="Lendo CSV e montando registros…")

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
                mensagem=f"Preparando registros… {idx}/{total_rows}",
            )

    campos_insert = list(dict.fromkeys([*mapeamento.keys(), *valores_padrao.keys()]))
    for extra in ("SITUACAO", "DATA_CADASTRO"):
        if extra not in campos_insert:
            campos_insert.append(extra)

    campos_upd = campos_para_update(
        mapeamento,
        atualizar_preco=atualizar_preco,
        atualizar_estoque=atualizar_estoque,
        atualizar_cadastro=atualizar_cadastro,
    )

    progresso.update(etapa="conexao", mensagem="Conectando no Firebird…")
    conn = conectar()
    try:
        cur = conn.cursor()
        ja = _existentes(cur, [r["CODIGO"] for r in registros])

        inseridos = atualizados = pulados = erros = 0
        log: list[str] = []
        erros_log: list[str] = []
        total = len(registros)
        acao = "Simulando" if dry_run else "Gravando"

        for i, reg in enumerate(registros, start=1):
            codigo = reg["CODIGO"]
            try:
                if codigo not in ja:
                    if not inserir_novos:
                        pulados += 1
                    else:
                        if reg.get("SITUACAO") is None:
                            reg["SITUACAO"] = "Ativo"
                        if reg.get("DATA_CADASTRO") is None:
                            reg["DATA_CADASTRO"] = date.today()
                        cols = ", ".join(campos_insert)
                        ph = ", ".join("?" * len(campos_insert))
                        vals = [reg.get(c) for c in campos_insert]
                        cur.execute(f"INSERT INTO ESTOQUE ({cols}) VALUES ({ph})", vals)
                        ja.add(codigo)  # código repetido no CSV vira UPDATE
                        inseridos += 1
                        if len(log) < 200:
                            log.append(f"INSERT {codigo}")
                else:
                    # ignora vazios: não sobrescreve dado existente com NULL
                    campos = [c for c in campos_upd if reg.get(c) is not None]
                    if not campos:
                        pulados += 1
                    else:
                        sets = ", ".join(f"{c} = ?" for c in campos)
                        vals = [reg[c] for c in campos] + [codigo]
                        cur.execute(f"UPDATE ESTOQUE SET {sets} WHERE CODIGO = ?", vals)
                        atualizados += 1
                        if len(log) < 200:
                            log.append(f"UPDATE {codigo} ({', '.join(campos)})")
            except Exception as e:
                erros += 1
                if len(erros_log) < 300:
                    erros_log.append(f"ERRO {codigo}: {e}")

            if i % 50 == 0 or i == total:
                progresso.update(
                    etapa="importacao",
                    atual=i,
                    total=total,
                    mensagem=(
                        f"{acao} {i}/{total} | "
                        f"ins={inseridos} upd={atualizados} err={erros} | "
                        f"atual: {codigo}"
                    ),
                )

        gravado = not dry_run and erros == 0
        if gravado:
            progresso.update(etapa="commit", mensagem="Confirmando transação (COMMIT)…")
            conn.commit()
            situacao = "COMMIT: alterações gravadas."
        else:
            progresso.update(etapa="rollback", mensagem="Desfazendo transação (ROLLBACK)…")
            conn.rollback()
            if dry_run:
                situacao = "ROLLBACK: simulação, nada gravado."
            else:
                situacao = f"ROLLBACK: {erros} erro(s), NADA foi gravado. Corrija e rode de novo."

        resultado = {
            "ok": True,
            "dry_run": dry_run,
            "gravado": gravado,
            "situacao": situacao,
            "atualizar_preco": atualizar_preco,
            "atualizar_estoque": atualizar_estoque,
            "atualizar_cadastro": atualizar_cadastro,
            "inserir_novos": inserir_novos,
            "campos_update": campos_upd,
            "inseridos": inseridos,
            "atualizados": atualizados,
            "pulados": pulados,
            "erros": erros,
            "log": erros_log + log,
        }
        progresso.update(
            etapa="fim",
            atual=total,
            total=total,
            mensagem=(
                f"{situacao} {inseridos} insert, {atualizados} update, {erros} erros"
            ),
        )
        return resultado
    finally:
        conn.close()
