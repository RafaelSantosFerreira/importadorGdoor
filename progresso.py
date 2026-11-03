from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_state: dict[str, Any] = {
    "rodando": False,
    "operacao": "",
    "etapa": "",
    "atual": 0,
    "total": 0,
    "percent": 0,
    "mensagem": "Aguardando…",
    "done": True,
    "erro": None,
    "resultado": None,
}


def snapshot() -> dict:
    with _lock:
        return dict(_state)


def reset(operacao: str, mensagem: str = "Iniciando…") -> None:
    with _lock:
        _state.update(
            {
                "rodando": True,
                "operacao": operacao,
                "etapa": "inicio",
                "atual": 0,
                "total": 0,
                "percent": 0,
                "mensagem": mensagem,
                "done": False,
                "erro": None,
                "resultado": None,
            }
        )


def update(
    *,
    etapa: str | None = None,
    atual: int | None = None,
    total: int | None = None,
    mensagem: str | None = None,
) -> None:
    with _lock:
        if etapa is not None:
            _state["etapa"] = etapa
        if atual is not None:
            _state["atual"] = atual
        if total is not None:
            _state["total"] = total
        if mensagem is not None:
            _state["mensagem"] = mensagem
        t = _state["total"]
        a = _state["atual"]
        _state["percent"] = int((a / t) * 100) if t else 0


def finish(resultado: dict | None = None, erro: str | None = None) -> None:
    with _lock:
        _state["rodando"] = False
        _state["done"] = True
        _state["resultado"] = resultado
        _state["erro"] = erro
        if erro is not None:
            _state["mensagem"] = f"Erro: {erro}" if erro else "Erro: falha sem mensagem"
            _state["etapa"] = "erro"
        else:
            _state["percent"] = 100
            _state["etapa"] = "fim"
            if not _state["mensagem"]:
                _state["mensagem"] = "Concluído"
