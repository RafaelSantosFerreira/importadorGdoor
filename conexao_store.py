from __future__ import annotations

import json
from pathlib import Path

from config import (
    BASE_DIR,
    CSV_DELIMITER,
    CSV_ENCODING,
    CSV_PADRAO,
    FB_CHARSET,
    FB_DATABASE,
    FB_HOST,
    FB_PASSWORD,
    FB_PORT,
    FB_USER,
)

CONEXAO_PATH = BASE_DIR / "conexao.json"

DEFAULTS = {
    "host": FB_HOST,
    "port": FB_PORT,
    "database": FB_DATABASE,
    "user": FB_USER,
    "password": FB_PASSWORD,
    "charset": FB_CHARSET,
    "csv": str(CSV_PADRAO),
    "csv_encoding": CSV_ENCODING,
    "csv_delimiter": CSV_DELIMITER,
}


def carregar() -> dict:
    data = dict(DEFAULTS)
    if CONEXAO_PATH.exists():
        salvos = json.loads(CONEXAO_PATH.read_text(encoding="utf-8"))
        data.update({k: v for k, v in salvos.items() if v is not None})
    data["port"] = int(data.get("port") or 3050)
    return data


def salvar(payload: dict) -> dict:
    data = dict(DEFAULTS)
    data.update(
        {
            "host": (payload.get("host") or DEFAULTS["host"]).strip(),
            "port": int(payload.get("port") or 3050),
            "database": (payload.get("database") or DEFAULTS["database"]).strip(),
            "user": (payload.get("user") or DEFAULTS["user"]).strip(),
            "password": payload.get("password")
            if payload.get("password") is not None
            else DEFAULTS["password"],
            "charset": (payload.get("charset") or DEFAULTS["charset"]).strip(),
            "csv": (payload.get("csv") or DEFAULTS["csv"]).strip(),
            "csv_encoding": (payload.get("csv_encoding") or DEFAULTS["csv_encoding"]).strip(),
            "csv_delimiter": payload.get("csv_delimiter") or DEFAULTS["csv_delimiter"],
        }
    )
    CONEXAO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
