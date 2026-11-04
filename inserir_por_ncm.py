"""Cadastra no ESTOQUE os produtos do CSV que faltam, copiando um produto modelo.

Para cada código do CSV sem correspondente no banco (mesmo casamento de
:mod:`faltantes`: ``cast(CODIGO as int) = cast(id_identificador as int)``):

1. Procura no ESTOQUE um produto com o mesmo NCM (comparando só os dígitos,
   ``1509.20.00`` == ``15092000``). Entre vários, o modelo é o de **maior
   CODIGO** que esteja ativo (SITUACAO = Ativo e sem DELETED_AT) — o mais novo.
2. Sem produto com aquele NCM, o item fica de fora e aparece no log como
   "sem modelo". O usuário escolhe na tela um produto para copiar e roda de novo
   (``escolhas = {codigo_csv: codigo_modelo}``); a escolha manual vale também
   para trocar o modelo achado pelo NCM.
3. Grava com ``INSERT INTO ESTOQUE (...) SELECT ... FROM ESTOQUE WHERE CODIGO =
   <modelo>``: todas as colunas vêm do modelo, menos as que vêm do CSV:

   - CODIGO       <- id_identificador (com zeros à esquerda, 6 posições)
   - DESCRICAO    <- descricao
   - PRECO_VENDA  <- prc_venda
   - saldo        <- qtd_atual (QTD_SALDO e QTD; QTD_DISPONIVEL se existir)
   - BARRAS       <- cod_barra

   e as que não podem ser copiadas: DATA_CADASTRO vira a data de hoje,
   DELETED_AT fica vazio, QTD_RESERVADA zera, e colunas calculadas, de
   identidade ou com índice único (fora CODIGO e BARRAS) ficam de fora para o
   banco preencher.

Uma única transação: simulação, ou qualquer erro, termina em ROLLBACK.
"""

from __future__ import annotations

import re
from decimal import Decimal

import progresso
from csv_origem import ler_linhas_csv
from db import conectar
from diferenca_campo import COLUNA_IDENTIFICADOR, como_int
from mapeamento_store import carregar as carregar_mapeamento
from transform import fmt_num, para_numero, trunc

LIMITE_ITENS = 5000
TAMANHO_CODIGO = 6

# Campo do ESTOQUE -> coluna do CSV quando o de-para não define nada.
COLUNAS_CSV = {
    "DESCRICAO": "descricao",
    "PRECO_VENDA": "prc_venda",
    "QTD": "qtd_atual",
    "BARRAS": "cod_barra",
    "COD_NCM": "cod_ncm",
}

# Colunas de saldo que recebem a quantidade do CSV (as que existirem).
COLUNAS_SALDO = ("QTD_SALDO", "QTD", "QTD_DISPONIVEL")
# Colunas de quantidade do modelo que não fazem sentido no produto novo.
COLUNAS_ZERAR = ("QTD_RESERVADA",)

_SO_DIGITOS = re.compile(r"\D")


def so_digitos(valor) -> str:
    return _SO_DIGITOS.sub("", str(valor or ""))


def codigo_banco(chave: int) -> str | None:
    """4152 -> '004152'; None quando não cabe no VARCHAR(6) do CODIGO."""
    texto = str(chave).zfill(TAMANHO_CODIGO)
    return texto if chave >= 0 and len(texto) <= TAMANHO_CODIGO else None


# ---------------------------------------------------------------- metadados
def _colunas_estoque(cur) -> list[dict]:
    cur.execute(
        """
        SELECT
            TRIM(rf.RDB$FIELD_NAME),
            CASE WHEN f.RDB$COMPUTED_BLR IS NULL THEN 0 ELSE 1 END,
            rf.RDB$IDENTITY_TYPE,
            COALESCE(f.RDB$CHARACTER_LENGTH, 0)
        FROM RDB$RELATION_FIELDS rf
        JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE
        WHERE TRIM(rf.RDB$RELATION_NAME) = 'ESTOQUE'
        ORDER BY rf.RDB$FIELD_POSITION
        """
    )
    return [
        {
            "nome": nome.strip(),
            "calculada": bool(calc),
            "identidade": ident is not None,
            "tamanho": int(tam or 0),
        }
        for nome, calc, ident, tam in cur.fetchall()
    ]


def _colunas_unicas(cur) -> set[str]:
    cur.execute(
        """
        SELECT TRIM(s.RDB$FIELD_NAME)
        FROM RDB$INDICES i
        JOIN RDB$INDEX_SEGMENTS s ON s.RDB$INDEX_NAME = i.RDB$INDEX_NAME
        WHERE TRIM(i.RDB$RELATION_NAME) = 'ESTOQUE' AND i.RDB$UNIQUE_FLAG = 1
        """
    )
    return {nome.strip() for (nome,) in cur.fetchall()}


def _montar_insert(cur) -> tuple[str, list[str], dict]:
    """SQL do INSERT ... SELECT e a ordem dos parâmetros."""
    colunas = _colunas_estoque(cur)
    existentes = {c["nome"] for c in colunas}
    unicas = _colunas_unicas(cur)

    do_csv = ["CODIGO", "DESCRICAO", "PRECO_VENDA", "BARRAS"]
    do_csv += [c for c in COLUNAS_SALDO if c in existentes]
    faltam = [c for c in ("CODIGO", "DESCRICAO", "PRECO_VENDA") if c not in existentes]
    if faltam:
        raise ValueError(f"ESTOQUE não tem a(s) coluna(s): {', '.join(faltam)}")

    destino: list[str] = []
    origem: list[str] = []
    params: list[str] = []
    fora: list[str] = []
    for c in colunas:
        nome = c["nome"]
        if c["calculada"] or c["identidade"]:
            fora.append(nome)
            continue
        if nome in do_csv:
            expr = f"CAST(? AS TYPE OF COLUMN ESTOQUE.{nome})"
            params.append(nome)
        elif nome == "DATA_CADASTRO":
            expr = "CURRENT_DATE"
        elif nome == "DELETED_AT":
            expr = "NULL"
        elif nome in COLUNAS_ZERAR:
            expr = "0"
        elif nome in unicas:
            fora.append(nome)  # copiar duplicaria a chave; o banco preenche
            continue
        else:
            expr = f"m.{nome}"
        destino.append(nome)
        origem.append(expr)

    sql = (
        f"INSERT INTO ESTOQUE ({', '.join(destino)}) "
        f"SELECT {', '.join(origem)} FROM ESTOQUE m WHERE m.CODIGO = ?"
    )
    info = {
        "tamanhos": {c["nome"]: c["tamanho"] for c in colunas},
        "existentes": existentes,
        "fora": fora,
        "do_csv": do_csv,
    }
    return sql, params, info


# ---------------------------------------------------------------- análise
def _ativo(situacao, deleted_at) -> bool:
    return deleted_at is None and str(situacao or "").strip().upper() == "ATIVO"


def _carregar_banco(cur, tem_deleted: bool) -> dict:
    deleted = "DELETED_AT" if tem_deleted else "NULL"
    cur.execute(
        f"SELECT CODIGO, COD_NCM, DESCRICAO, SITUACAO, {deleted}, BARRAS FROM ESTOQUE"
    )
    codigos: set[int] = set()
    produtos: dict[str, dict] = {}  # CODIGO exato (sem espaços) -> dados
    por_ncm: dict[str, tuple[int, str]] = {}  # ncm -> (chave int, CODIGO exato)
    barras: set[str] = set()
    for codigo, ncm, descricao, situacao, deleted_at, bar in cur.fetchall():
        exato = str(codigo or "").strip()
        chave = como_int(exato)
        if chave is not None:
            codigos.add(chave)
        if bar and str(bar).strip():
            barras.add(str(bar).strip())
        produtos[exato] = {
            "codigo": exato,
            "descricao": (descricao or "").strip(),
            "ncm": so_digitos(ncm),
            "ativo": _ativo(situacao, deleted_at),
        }
        digitos = so_digitos(ncm)
        if digitos and chave is not None and _ativo(situacao, deleted_at):
            atual = por_ncm.get(digitos)
            if atual is None or chave > atual[0]:
                por_ncm[digitos] = (chave, exato)
    return {"codigos": codigos, "produtos": produtos, "por_ncm": por_ncm, "barras": barras}


def _achar_modelo(produtos: dict, codigo: str) -> dict | None:
    texto = str(codigo or "").strip()
    if not texto:
        return None
    if texto in produtos:
        return produtos[texto]
    chave = como_int(texto)
    if chave is not None:
        exato = codigo_banco(chave)
        if exato in produtos:
            return produtos[exato]
    return None


def _analisar(cur, rows: list[dict], col: dict[str, str], escolhas: dict, info: dict) -> dict:
    banco = _carregar_banco(cur, "DELETED_AT" in info["existentes"])
    produtos = banco["produtos"]
    tam_desc = info["tamanhos"].get("DESCRICAO") or None
    tam_barras = info["tamanhos"].get("BARRAS") or None

    itens: list[dict] = []
    existentes = sem_codigo = duplicados = 0
    vistos: set[int] = set()
    barras_novas: set[str] = set()
    total = len(rows)

    def texto(row, campo):
        return (row.get(col[campo]) or "").strip()

    for i, row in enumerate(rows, start=1):
        bruto = (row.get(COLUNA_IDENTIFICADOR) or "").strip()
        chave = como_int(bruto)
        if chave is None:
            sem_codigo += 1
        elif chave in vistos:
            duplicados += 1
        elif chave in banco["codigos"]:
            existentes += 1
        else:
            ncm = so_digitos(texto(row, "COD_NCM"))
            preco = para_numero(texto(row, "PRECO_VENDA")) or Decimal(0)
            qtd = para_numero(texto(row, "QTD")) or Decimal(0)
            barras = trunc(texto(row, "BARRAS"), tam_barras)
            descricao = trunc(texto(row, "DESCRICAO"), tam_desc) or "SEM DESCRICAO"
            codigo_novo = codigo_banco(chave)

            escolha = (escolhas or {}).get(bruto) or (escolhas or {}).get(str(chave))
            modelo = None
            origem = ""
            motivo = ""
            if codigo_novo is None:
                motivo = f"código com mais de {TAMANHO_CODIGO} dígitos"
            elif escolha:
                modelo = _achar_modelo(produtos, escolha)
                origem = "escolhido"
                if modelo is None:
                    motivo = f"modelo escolhido {escolha} não existe no banco"
            elif ncm and ncm in banco["por_ncm"]:
                modelo = produtos[banco["por_ncm"][ncm][1]]
                origem = "ncm"
            else:
                motivo = (
                    f"nenhum produto ativo com NCM {ncm} — selecione um para copiar"
                    if ncm
                    else "sem NCM no CSV — selecione um produto para copiar"
                )

            avisos = []
            if barras and (barras in banco["barras"] or barras in barras_novas):
                avisos.append("código de barras já existe")
            if qtd < 0:
                avisos.append("saldo negativo")
            if modelo is not None and not motivo and barras:
                barras_novas.add(barras)

            if len(itens) < LIMITE_ITENS:
                itens.append(
                    {
                        "codigo": bruto,
                        "codigo_banco": codigo_novo or "",
                        "descricao": descricao,
                        "ncm": ncm,
                        "barras": barras or "",
                        "preco_venda": fmt_num(preco),
                        "qtd": fmt_num(qtd),
                        "linha": i + 1,  # +1 por causa do cabeçalho
                        "modelo": modelo["codigo"] if modelo and not motivo else "",
                        "modelo_descricao": modelo["descricao"] if modelo and not motivo else "",
                        "modelo_ncm": modelo["ncm"] if modelo and not motivo else "",
                        "origem_modelo": origem if not motivo else "",
                        "pronto": bool(modelo) and not motivo,
                        "motivo": motivo,
                        "avisos": avisos,
                        "_preco": preco,
                        "_qtd": qtd,
                    }
                )
        if chave is not None:
            vistos.add(chave)

        if i % 500 == 0 or i == total:
            progresso.update(
                etapa="analise",
                atual=i,
                total=total,
                mensagem=f"Procurando modelos {i}/{total} | faltando={len(itens)}",
            )

    return {
        "itens": itens,
        "linhas_csv": total,
        "existentes": existentes,
        "sem_codigo": sem_codigo,
        "duplicados": duplicados,
    }


def _preparar() -> tuple[list[dict], dict[str, str]]:
    progresso.update(etapa="csv", mensagem="Lendo CSV…")
    cfg = carregar_mapeamento()
    mapeamento = cfg.get("mapeamento") or {}
    col = {campo: mapeamento.get(campo) or padrao for campo, padrao in COLUNAS_CSV.items()}
    rows = ler_linhas_csv(cfg.get("csv"))
    if rows:
        for nome in (COLUNA_IDENTIFICADOR, col["COD_NCM"], col["DESCRICAO"]):
            if nome not in rows[0]:
                raise ValueError(f"Coluna '{nome}' não existe no CSV.")
    return rows, col


def _limpar(itens: list[dict]) -> list[dict]:
    return [{k: v for k, v in it.items() if not k.startswith("_")} for it in itens]


def _resumo(dados: dict) -> dict:
    itens = dados["itens"]
    prontos = sum(1 for it in itens if it["pronto"])
    return {
        "linhas_csv": dados["linhas_csv"],
        "existentes": dados["existentes"],
        "sem_codigo": dados["sem_codigo"],
        "duplicados": dados["duplicados"],
        "faltando": len(itens),
        "com_modelo": prontos,
        "sem_modelo": len(itens) - prontos,
        "truncado": len(itens) >= LIMITE_ITENS,
    }


def _log_sem_modelo(itens: list[dict]) -> list[str]:
    return [
        f"SEM MODELO {it['codigo']} ({it['descricao']}): {it['motivo']}"
        for it in itens
        if not it["pronto"]
    ]


# ---------------------------------------------------------------- operações
def previa(escolhas: dict | None = None) -> dict:
    """Só leitura: lista os faltantes e o modelo que cada um vai copiar."""
    rows, col = _preparar()
    progresso.update(etapa="conexao", mensagem="Lendo produtos do banco…")
    conn = conectar()
    try:
        cur = conn.cursor()
        _sql, _params, info = _montar_insert(cur)
        dados = _analisar(cur, rows, col, escolhas or {}, info)
    finally:
        conn.close()

    r = _resumo(dados)
    msg = (
        f"{r['faltando']} faltando: {r['com_modelo']} com modelo, "
        f"{r['sem_modelo']} sem modelo (selecione um para copiar)."
        if r["faltando"]
        else "Todos os códigos do CSV já existem no banco."
    )
    progresso.update(etapa="fim", mensagem=msg)
    return {
        "ok": True,
        "modo": "ncm_previa",
        "situacao": msg,
        **r,
        "colunas_csv": col,
        "colunas_fora": info["fora"],
        "itens": _limpar(dados["itens"]),
        "log": _log_sem_modelo(dados["itens"])[:300],
    }


def aplicar(*, dry_run: bool = True, escolhas: dict | None = None) -> dict:
    """Insere os faltantes que têm modelo. Simulação ou erro => ROLLBACK."""
    rows, col = _preparar()
    progresso.update(etapa="conexao", mensagem="Lendo produtos do banco…")
    conn = conectar()
    try:
        cur = conn.cursor()
        sql, params, info = _montar_insert(cur)
        dados = _analisar(cur, rows, col, escolhas or {}, info)

        alvos = [it for it in dados["itens"] if it["pronto"]]
        inseridos = erros = 0
        log: list[str] = []
        erros_log: list[str] = []
        acao = "Simulando" if dry_run else "Inserindo"
        total = len(alvos)

        for i, it in enumerate(alvos, start=1):
            valores = {
                "CODIGO": it["codigo_banco"],
                "DESCRICAO": it["descricao"],
                "PRECO_VENDA": it["_preco"],
                "BARRAS": it["barras"] or None,
                **{c: it["_qtd"] for c in COLUNAS_SALDO},
            }
            try:
                cur.execute(sql, [valores[p] for p in params] + [it["modelo"]])
                if getattr(cur, "rowcount", -1) == 0:
                    raise RuntimeError(f"modelo {it['modelo']} não encontrado")
                inseridos += 1
                if len(log) < 300:
                    log.append(
                        f"INSERT {it['codigo_banco']} {it['descricao']} "
                        f"<- modelo {it['modelo']} ({it['origem_modelo']})"
                    )
            except Exception as e:
                erros += 1
                if len(erros_log) < 300:
                    erros_log.append(f"ERRO {it['codigo']}: {e or type(e).__name__}")

            if i % 100 == 0 or i == total:
                progresso.update(
                    etapa="gravacao",
                    atual=i,
                    total=total,
                    mensagem=f"{acao} {i}/{total} | inseridos={inseridos} erros={erros}",
                )

        gravado = not dry_run and erros == 0 and inseridos > 0
        if gravado:
            conn.commit()
            situacao = f"COMMIT: {inseridos} produto(s) inserido(s)."
        else:
            conn.rollback()
            if dry_run:
                situacao = "ROLLBACK: simulação, nada gravado."
            elif erros:
                situacao = f"ROLLBACK: {erros} erro(s), NADA foi gravado."
            else:
                situacao = "Nada para inserir."

        r = _resumo(dados)
        progresso.update(etapa="fim", atual=total, total=total, mensagem=situacao)
        return {
            "ok": True,
            "modo": "ncm_aplicar",
            "dry_run": dry_run,
            "gravado": gravado,
            "situacao": situacao,
            **r,
            "inseridos": inseridos,
            "erros": erros,
            "colunas_csv": col,
            "colunas_fora": info["fora"],
            "itens": _limpar(dados["itens"]),
            "log": erros_log + _log_sem_modelo(dados["itens"])[:300] + log,
        }
    finally:
        conn.close()
