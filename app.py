from __future__ import annotations

import threading

from flask import Flask, jsonify, render_template, request

import progresso
from comparar import comparar_preco_estoque
from conexao_store import carregar as carregar_conexao
from conexao_store import salvar as salvar_conexao
from csv_origem import ler_cabecalho_e_amostra
from db import listar_campos_estoque, listar_valores_distintos, testar_conexao
from diferenca_preco import aplicar_diferencas_preco, buscar_diferencas_preco
from importar_service import importar
from mapeamento_store import aplicar_sugestao, carregar as carregar_mapeamento
from mapeamento_store import salvar as salvar_mapeamento

app = Flask(__name__)
_job_lock = threading.Lock()


@app.get("/")
def index():
    return render_template("conexao.html", ativo="conexao")


@app.get("/depara")
def depara():
    return render_template("mapeamento.html", ativo="depara")


@app.get("/importacao")
def importacao():
    return render_template("importacao.html", ativo="importacao")


# ---- Conexão ----
@app.get("/api/conexao")
def api_conexao_get():
    data = carregar_conexao()
    # não esconde senha na rede local do migrador; UI precisa editar
    return jsonify({"ok": True, **data})


@app.post("/api/conexao")
def api_conexao_post():
    payload = request.get_json(force=True) or {}
    data = salvar_conexao(payload)
    return jsonify({"ok": True, **data})


@app.post("/api/conexao/testar")
def api_conexao_testar():
    payload = request.get_json(force=True) or {}
    cfg = carregar_conexao()
    if payload:
        cfg = {**cfg, **payload}
        if payload.get("port") is not None:
            cfg["port"] = int(payload["port"])
    try:
        result = testar_conexao(cfg)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 400


# ---- Origem / Destino / De-para ----
@app.get("/api/origem")
def api_origem():
    csv_path = request.args.get("csv") or None
    try:
        data = ler_cabecalho_e_amostra(csv_path)
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 400


@app.get("/api/destino")
def api_destino():
    try:
        campos = listar_campos_estoque()
        return jsonify({"ok": True, "tabela": "ESTOQUE", "campos": campos})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


@app.get("/api/destino/<campo>/valores")
def api_destino_valores(campo: str):
    try:
        valores = listar_valores_distintos(campo)
        return jsonify(
            {
                "ok": True,
                "tabela": "ESTOQUE",
                "campo": campo.upper(),
                "valores": valores,
                "total": len(valores),
            }
        )
    except ValueError as e:
        return jsonify({"ok": False, "erro": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


@app.get("/api/mapeamento")
def api_mapeamento_get():
    data = carregar_mapeamento()
    return jsonify({"ok": True, **data})


@app.post("/api/mapeamento")
def api_mapeamento_post():
    payload = request.get_json(force=True) or {}
    # sincroniza csv da conexão se não veio no payload
    if not payload.get("csv"):
        payload["csv"] = carregar_conexao().get("csv")
    data = salvar_mapeamento(payload)
    return jsonify({"ok": True, **data})


@app.post("/api/mapeamento/sugerir")
def api_mapeamento_sugerir():
    payload = request.get_json(force=True) or {}
    colunas = payload.get("colunas") or []
    if not colunas:
        origem = ler_cabecalho_e_amostra(payload.get("csv"))
        colunas = [c["nome"] for c in origem["colunas"]]
    sugestao = aplicar_sugestao(colunas)
    return jsonify({"ok": True, **sugestao})


# ---- Comparação / Importação / Progresso ----
@app.get("/api/progresso")
def api_progresso():
    return jsonify({"ok": True, **progresso.snapshot()})


def _iniciar_job(nome: str, mensagem: str, alvo) -> tuple[bool, str]:
    with _job_lock:
        atual = progresso.snapshot()
        if atual.get("rodando"):
            return False, "Já existe uma operação em andamento."
        progresso.reset(nome, mensagem)
    threading.Thread(target=alvo, daemon=True).start()
    return True, "ok"


@app.post("/api/comparar")
def api_comparar():
    def worker():
        try:
            data = comparar_preco_estoque()
            progresso.finish({"ok": True, **data})
        except Exception as e:
            progresso.finish(erro=str(e) or type(e).__name__)

    ok, msg = _iniciar_job("comparar", "Iniciando comparação…", worker)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 409
    return jsonify({"ok": True, "started": True})


@app.post("/api/importar")
def api_importar():
    payload = request.get_json(force=True) or {}
    atualizar_preco = bool(payload.get("atualizar_preco", True))
    atualizar_estoque = bool(payload.get("atualizar_estoque", True))
    atualizar_cadastro = bool(payload.get("atualizar_cadastro", False))
    inserir_novos = bool(payload.get("inserir_novos", True))
    dry_run = bool(payload.get("dry_run", True))

    def worker():
        try:
            data = importar(
                atualizar_preco=atualizar_preco,
                atualizar_estoque=atualizar_estoque,
                atualizar_cadastro=atualizar_cadastro,
                inserir_novos=inserir_novos,
                dry_run=dry_run,
            )
            progresso.finish(data)
        except Exception as e:
            progresso.finish(erro=str(e) or type(e).__name__)

    titulo = "Simulando importação…" if dry_run else "Aplicando importação no banco…"
    ok, msg = _iniciar_job("importar", titulo, worker)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 409
    return jsonify({"ok": True, "started": True, "dry_run": dry_run})


@app.post("/api/preco/diferencas")
def api_preco_diferencas():
    """Só leitura: lista PRECO_VENDA <> prc_venda casando por id_identificador."""

    def worker():
        try:
            progresso.finish(buscar_diferencas_preco())
        except Exception as e:
            progresso.finish(erro=str(e) or type(e).__name__)

    ok, msg = _iniciar_job("dif_preco", "Buscando diferenças de preço…", worker)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 409
    return jsonify({"ok": True, "started": True})


@app.post("/api/preco/diferencas/aplicar")
def api_preco_diferencas_aplicar():
    payload = request.get_json(force=True) or {}
    dry_run = bool(payload.get("dry_run", True))

    def worker():
        try:
            progresso.finish(aplicar_diferencas_preco(dry_run=dry_run))
        except Exception as e:
            progresso.finish(erro=str(e) or type(e).__name__)

    titulo = "Simulando preços do CSV…" if dry_run else "Gravando preços do CSV…"
    ok, msg = _iniciar_job("dif_preco_aplicar", titulo, worker)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 409
    return jsonify({"ok": True, "started": True, "dry_run": dry_run})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
