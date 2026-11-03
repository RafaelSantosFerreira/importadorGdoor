from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Firebird destino
FB_HOST = "localhost"
FB_PORT = 3050
FB_DATABASE = r"F:\jorgeFb\DATAGES.FDB"
FB_USER = "SYSDBA"
FB_PASSWORD = "masterkey"
FB_CHARSET = "WIN1252"

# CSV origem padrão
CSV_PADRAO = BASE_DIR / "produtos_20261103155732.csv"
CSV_ENCODING = "latin-1"
CSV_DELIMITER = ";"

# Arquivo de mapeamento de-para
MAPEAMENTO_PATH = BASE_DIR / "mapeamento_estoque.json"

# Campos ESTOQUE que não devem aparecer no de-para (blobs / internos)
CAMPOS_IGNORADOS = {
    "FOTO",
    "OBSERVACOES",
    "OBS_TEXTO",
    "GRADE_QUA",
    "GRADE_DIS",
    "GRADE_QTD_PEDCOM",
    "GRADE_DIS_PEDCOM",
    "GRADE_QTD_PEDVEN",
    "GRADE_DIS_PEDVEN",
    "GRADE_QUA_IDEAL",
    "GRADE_DIS_IDEAL",
    "UPDATED_AT",
    "DELETED_AT",
}

# Sugestão inicial CSV -> ESTOQUE
MAPEAMENTO_SUGERIDO = {
    "CODIGO": "id_estoque",
    "BARRAS": "cod_barra",
    "DESCRICAO": "descricao",
    "UND": "uni_medida",
    "FAMILIA": "familia",
    "GRUPO": "grupo",
    "FORNECEDOR": "nome",
    "PESO": "peso",
    "QTD": "qtd_atual",
    "QTD_INICIAL": "qtd_inicio",
    "QTD_IDEAL": "qtd_minim",
    "CUSTO_MEDIO": "custo_medio",
    "PRECO_CUSTO": "prc_custo",
    "MARGEM_LUCRO": "margem_lb",
    "PRECO_VENDA": "prc_venda",
    "PRECO_ATACADO": "prc_atacado",
    "COMISSAO": "por_comissao",
    "ST": "csosn",
    "CF": "cf",
    "ALIQ_IPI": "ipi",
    "PIS_CODIGO": "cst_pis",
    "COFINS_CODIGO": "cst_cofins",
    "PIS_ALIQ_NOR": "pis",
    "COFINS_ALIQ_NOR": "cofins",
    "ULTIMA_COMPRA": "ult_compra",
    "ULTIMA_VENDA": "utl_venda",
    "COD_FABRICANTE": "referencia",
    "COD_NCM": "cod_ncm",
    "COD_ANP": "anp",
    "IPPT": "ippt",
    "COD_FCI": "fci",
    "TIPO_ITEM": "tipo_item",
    "PERSONAL1": "adicional1",
    "PERSONAL2": "adicional2",
    "CBENEF": "cofBenef",
    "CODIGO_NBS": "cod_nbs",
}

# Valores padrão sugeridos quando o campo não tem origem no CSV
VALORES_PADRAO_SUGERIDOS = {
    "SITUACAO": "Ativo",
    "IPPT": "T",
    "TIPO_ITEM": "00 Mercadoria para Revenda",
    "FAT_CONV": "1",
    "VENDA_FRACIONADA": "1",
}
