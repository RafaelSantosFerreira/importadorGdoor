"""Backup do banco Firebird (.fbk) pela API de serviços — o mesmo que o gbak faz.

Roda com o banco em uso, sem parar o serviço, e gera um arquivo consistente
(cópia do .FDB com o servidor ligado não é segura). Quem grava o arquivo é o
próprio servidor Firebird, por isso o caminho é o da máquina do servidor; com
servidor local, cai na pasta ``backup/`` do projeto.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import firebirdsql.services

import progresso
from config import BASE_DIR
from conexao_store import carregar as carregar_conexao

PASTA_BACKUP = BASE_DIR / "backup"
LIMITE_LISTA = 20


def _servidor_local(host: str) -> bool:
    return (host or "").strip().lower() in ("", "localhost", "127.0.0.1", "::1")


def _arquivo_destino(database: str) -> Path:
    nome = Path(database.replace("\\", "/")).stem or "banco"
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PASTA_BACKUP / f"{nome}_{carimbo}.fbk"


def fazer_backup() -> dict:
    cfg = carregar_conexao()
    if not _servidor_local(cfg.get("host")):
        raise ValueError(
            "Backup pela tela só com o Firebird nesta máquina (host localhost): "
            "o arquivo é gravado pelo servidor, no disco dele."
        )

    PASTA_BACKUP.mkdir(exist_ok=True)
    destino = _arquivo_destino(cfg["database"])
    linhas: list[str] = []

    def andamento(msg: str) -> None:
        linhas.append(msg)
        if len(linhas) % 25 == 0:
            ultima = msg.strip()[:80]
            progresso.update(mensagem=f"Gerando backup… {len(linhas)} etapas | {ultima}")

    progresso.update(etapa="backup", mensagem=f"Gerando backup em {destino.name}…")
    inicio = datetime.now()
    svc = firebirdsql.services.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
    )
    try:
        svc.backup_database(cfg["database"], str(destino), callback=andamento)
    finally:
        svc.close()

    if not destino.exists() or destino.stat().st_size == 0:
        erro = next((l for l in reversed(linhas) if "ERROR" in l.upper()), "")
        raise RuntimeError(f"O Firebird não gerou o arquivo de backup. {erro}".strip())

    segundos = (datetime.now() - inicio).total_seconds()
    tamanho = destino.stat().st_size
    msg = f"Backup gerado: {destino.name} ({tamanho / 1024 / 1024:.1f} MB em {segundos:.0f}s)."
    progresso.update(etapa="fim", mensagem=msg)
    return {
        "ok": True,
        "modo": "backup",
        "situacao": msg,
        "arquivo": str(destino),
        "nome": destino.name,
        "tamanho": tamanho,
        "segundos": round(segundos, 1),
        "backups": listar_backups(),
    }


def listar_backups() -> list[dict]:
    if not PASTA_BACKUP.exists():
        return []
    arquivos = sorted(PASTA_BACKUP.glob("*.fbk"), key=lambda a: a.stat().st_mtime, reverse=True)
    return [
        {
            "nome": a.name,
            "arquivo": str(a),
            "tamanho": a.stat().st_size,
            "data": datetime.fromtimestamp(a.stat().st_mtime).strftime("%d/%m/%Y %H:%M:%S"),
        }
        for a in arquivos[:LIMITE_LISTA]
    ]
