from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def trunc(valor: str | None, tamanho: int | None) -> str | None:
    if valor is None:
        return None
    v = str(valor).strip()
    if not v:
        return None
    if tamanho:
        return v[:tamanho]
    return v


def para_numero(valor: str | None) -> Decimal | None:
    if valor is None or not str(valor).strip():
        return None
    txt = str(valor).strip()
    if "," in txt and "." in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif "," in txt:
        txt = txt.replace(",", ".")
    try:
        return Decimal(txt)
    except InvalidOperation:
        return None


def para_data(valor: str | None) -> date | None:
    if not valor or not str(valor).strip():
        return None
    txt = str(valor).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
    return None


def limpar_codigo(valor: str | None) -> str | None:
    v = trunc(valor, 6)
    if not v:
        return None
    if v.isdigit():
        return v.zfill(6)
    return v


TRANSFORMERS = {
    "CODIGO": limpar_codigo,
    "BARRAS": lambda v: trunc(v, 20),
    "DESCRICAO": lambda v: trunc(v, 120),
    "UND": lambda v: trunc(v, 6),
    "UND_COMPRA": lambda v: trunc(v, 6),
    "FAMILIA": lambda v: trunc(v, 40),
    "GRUPO": lambda v: trunc(v, 124),
    "FORNECEDOR": lambda v: trunc(v, 60),
    "COD_FABRICANTE": lambda v: trunc(v, 60),
    "COD_NCM": lambda v: trunc(v, 10),
    "COD_ANP": lambda v: trunc(v, 9),
    "COD_FCI": lambda v: trunc(v, 36),
    "ST": lambda v: trunc(v, 3),
    "CF": lambda v: trunc(v, 13),
    "IPPT": lambda v: trunc(v, 1),
    "TIPO_ITEM": lambda v: trunc(v, 30),
    "PERSONAL1": lambda v: trunc(v, 30),
    "PERSONAL2": lambda v: trunc(v, 30),
    "CBENEF": lambda v: trunc(v, 30),
    "CODIGO_NBS": lambda v: trunc(v, 9),
    "PIS_CODIGO": lambda v: trunc(v, 2),
    "COFINS_CODIGO": lambda v: trunc(v, 2),
    "SITUACAO": lambda v: trunc(v, 7),
    "PRECO_CUSTO": para_numero,
    "PRECO_VENDA": para_numero,
    "PRECO_ATACADO": para_numero,
    "CUSTO_MEDIO": para_numero,
    "MARGEM_LUCRO": para_numero,
    "COMISSAO": para_numero,
    "PESO": para_numero,
    "QTD": para_numero,
    "QTD_INICIAL": para_numero,
    "QTD_IDEAL": para_numero,
    "QTD_DISPONIVEL": para_numero,
    "ALIQ_IPI": para_numero,
    "PIS_ALIQ_NOR": para_numero,
    "COFINS_ALIQ_NOR": para_numero,
    "FAT_CONV": para_numero,
    "VENDA_FRACIONADA": para_numero,
    "ULTIMA_COMPRA": para_data,
    "ULTIMA_VENDA": para_data,
}

CAMPOS_PRECO = ("PRECO_VENDA", "PRECO_CUSTO", "PRECO_ATACADO", "CUSTO_MEDIO")
CAMPOS_ESTOQUE = ("QTD", "QTD_DISPONIVEL", "QTD_INICIAL")


def aplicar_valor(destino: str, bruto: str | None):
    transform = TRANSFORMERS.get(destino)
    if transform:
        return transform(bruto)
    return trunc(bruto, None) if bruto not in (None, "") else None


def montar_registro(
    row: dict[str, str],
    mapeamento: dict[str, str],
    valores_padrao: dict[str, str],
) -> dict:
    reg = {}
    for destino, origem in mapeamento.items():
        reg[destino] = aplicar_valor(destino, row.get(origem))
    for destino, padrao in valores_padrao.items():
        if destino in mapeamento:
            continue
        reg[destino] = aplicar_valor(destino, padrao)
    if not reg.get("CODIGO"):
        return {}
    if not reg.get("DESCRICAO"):
        reg["DESCRICAO"] = valores_padrao.get("DESCRICAO") or "SEM DESCRICAO"
    if "SITUACAO" not in reg:
        reg["SITUACAO"] = "Ativo"
    if "DATA_CADASTRO" not in reg:
        reg["DATA_CADASTRO"] = date.today()
    return reg


def num_eq(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except Exception:
        return str(a).strip() == str(b).strip()


def fmt_num(v) -> str:
    if v is None:
        return ""
    try:
        d = Decimal(str(v))
        return format(d.normalize(), "f")
    except Exception:
        return str(v)
