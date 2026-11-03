"""Faz FN_VALIDA_BARCODE parar de depender da UDF MOD de ib_udf.

Por que
-------
FN_VALIDA_BARCODE usa MOD, que neste banco está declarada como UDF legada de
``ib_udf``. O Firebird 5 não carrega UDF por padrão e não distribui mais essa
biblioteca, então o trigger TR_ESTOQUE_BARRAS derruba QUALQUER gravação no
ESTOQUE com "function MOD is not defined" — e nem dá para desativar o trigger,
porque ALTER TRIGGER revalida o corpo e cai no mesmo erro.

O Firebird tem MOD nativo desde a versão 2.1. O problema é só a declaração da
UDF, que tem precedência sobre a função interna.

O que faz
---------
1. ALTER FUNCTION com o MOD escrito como aritmética  -> tira a dependência
2. DROP EXTERNAL FUNCTION MOD                        -> remove a declaração
3. ALTER FUNCTION de volta ao corpo ORIGINAL         -> MOD agora é o nativo

No fim o corpo da função é idêntico ao que o Gdoor instalou; muda só de onde
vem o MOD. Depois valida o resultado contra o algoritmo EAN calculado aqui,
usando os códigos de barras que já estão no ESTOQUE.

Antes de rodar
--------------
Faça backup:

    "C:\\Program Files\\Firebird\\Firebird_5_0\\gbak.exe" -b -user SYSDBA \\
        -password masterkey "localhost:C:\\works\\importadorGdoor\\db\\DATAGES.FDB" \\
        "C:\\works\\importadorGdoor\\db\\backup.fbk"

Uso
---
    python corrigir_udf_mod.py            # mostra o diagnóstico, não altera nada
    python corrigir_udf_mod.py --aplicar  # aplica a correção
"""

from __future__ import annotations

import sys

from db import conectar

CABECA = "ALTER FUNCTION FN_VALIDA_BARCODE(P_CODIGO VARCHAR(20))\nRETURNS SMALLINT\nAS\n"

MIOLO = """DECLARE VARIABLE V_LEN    INTEGER;
DECLARE VARIABLE V_SOMA   INTEGER;
DECLARE VARIABLE V_DIGITO INTEGER;
DECLARE VARIABLE V_CALC   INTEGER;
DECLARE VARIABLE V_PESO   INTEGER;
DECLARE VARIABLE I        INTEGER;
BEGIN
  V_LEN = CHAR_LENGTH(TRIM(P_CODIGO));
  IF (V_LEN NOT IN (8, 13)) THEN RETURN 0;
  IF (P_CODIGO SIMILAR TO '[^0-9]+') THEN RETURN 0;
  V_SOMA = 0;
  I = 1;
  WHILE (I < V_LEN) DO
  BEGIN
    IF (V_LEN = 13) THEN
      V_PESO = CASE WHEN {mod_i2} = 1 THEN 1 ELSE 3 END;
    ELSE
      V_PESO = CASE WHEN {mod_i2} = 1 THEN 3 ELSE 1 END;
    V_SOMA = V_SOMA + CAST(SUBSTRING(P_CODIGO FROM I FOR 1) AS INTEGER) * V_PESO;
    I = I + 1;
  END
  V_CALC   = {mod_soma10};
  V_DIGITO = CASE WHEN V_CALC = 0 THEN 0 ELSE 10 - V_CALC END;
  IF (V_DIGITO = CAST(SUBSTRING(P_CODIGO FROM V_LEN FOR 1) AS INTEGER)) THEN
    RETURN 1;
  ELSE
    RETURN 0;
END"""

SEM_MOD = CABECA + MIOLO.format(
    mod_i2="(I - (I / 2) * 2)", mod_soma10="(V_SOMA - (V_SOMA / 10) * 10)"
)
ORIGINAL = CABECA + MIOLO.format(mod_i2="MOD(I, 2)", mod_soma10="MOD(V_SOMA, 10)")


def _uma(sql, params=()):
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(sql, params) if params else cur.execute(sql)
        return cur.fetchone()
    finally:
        conn.close()


def udf_mod_declarada() -> bool:
    row = _uma(
        "select count(*) from rdb$functions "
        "where trim(rdb$function_name)='MOD' and rdb$legacy_flag = 1"
    )
    return bool(row[0])


def grava_no_estoque() -> tuple[bool, str]:
    """Tenta um UPDATE inócuo e desfaz. Diz se o trigger deixa gravar."""
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE ESTOQUE SET PRECO_VENDA = PRECO_VENDA WHERE CODIGO = ?", ("000078",))
        conn.rollback()
        return True, "passa"
    except Exception as e:
        conn.rollback()
        return False, str(e).strip().splitlines()[0]
    finally:
        conn.close()


def executar(rotulo: str, sql: str) -> bool:
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        print(f"  {rotulo}: ok")
        return True
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"  {rotulo}: FALHOU -> {str(e).strip().splitlines()[0]}")
        return False
    finally:
        conn.close()


def digito_ean(codigo: str) -> int:
    """Dígito verificador de EAN-8/EAN-13, para conferir a função do banco."""
    corpo = codigo[:-1]
    n = len(codigo)
    soma = 0
    for i, ch in enumerate(corpo, start=1):
        if n == 13:
            peso = 1 if i % 2 == 1 else 3
        else:
            peso = 3 if i % 2 == 1 else 1
        soma += int(ch) * peso
    resto = soma % 10
    return 0 if resto == 0 else 10 - resto


def validar() -> bool:
    """Compara a função do banco com o algoritmo EAN, em códigos reais."""
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT FIRST 200 BARRAS FROM ESTOQUE "
            "WHERE BARRAS IS NOT NULL AND CHAR_LENGTH(TRIM(BARRAS)) IN (8, 13)"
        )
        codigos = [c.strip() for (c,) in cur.fetchall() if c and c.strip().isdigit()]
        # alguns casos construídos: válido, inválido e formato errado
        extras = ["7891150198906", "7891150198900", "1234567", "ABCDEFGHIJKLM", "40170725"]
        testados = divergentes = 0
        for codigo in codigos + extras:
            cur.execute("SELECT FN_VALIDA_BARCODE(?) FROM RDB$DATABASE", (codigo,))
            doBanco = int(cur.fetchone()[0])
            if len(codigo) in (8, 13) and codigo.isdigit():
                esperado = 1 if digito_ean(codigo) == int(codigo[-1]) else 0
            else:
                esperado = 0
            testados += 1
            if doBanco != esperado:
                divergentes += 1
                print(f"    DIVERGE {codigo}: banco={doBanco} esperado={esperado}")
        print(f"  conferidos {testados} códigos, {divergentes} divergência(s)")
        return divergentes == 0
    finally:
        conn.close()


def main() -> int:
    aplicar = "--aplicar" in sys.argv

    print("=== estado atual ===")
    declarada = udf_mod_declarada()
    ok_grava, detalhe = grava_no_estoque()
    print(f"  UDF MOD declarada ........ {declarada}")
    print(f"  grava no ESTOQUE ......... {ok_grava}" + ("" if ok_grava else f"  ({detalhe})"))

    if not declarada:
        print("\nA declaração da UDF MOD já não existe; nada a fazer.")
        return 0

    if not aplicar:
        print("\nNada foi alterado. Para aplicar a correção:")
        print("    python corrigir_udf_mod.py --aplicar")
        print("Faça backup antes (veja o cabeçalho deste arquivo).")
        return 0

    print("\n=== aplicando ===")
    print("passo 1 — ALTER FUNCTION sem usar MOD")
    if not executar("ALTER FUNCTION", SEM_MOD):
        print("\nNada foi alterado.")
        return 1

    print("passo 2 — DROP EXTERNAL FUNCTION MOD")
    if not executar("DROP EXTERNAL FUNCTION MOD", "DROP EXTERNAL FUNCTION MOD"):
        print("  a função já não depende da UDF; seguindo")

    print("passo 3 — ALTER FUNCTION de volta ao corpo original (MOD nativo)")
    if not executar("ALTER FUNCTION", ORIGINAL):
        print("  o corpo fica na versão aritmética, que é equivalente")

    print("\n=== validação ===")
    certo = validar()
    ok_grava, detalhe = grava_no_estoque()
    print(f"  UDF MOD declarada ........ {udf_mod_declarada()}")
    print(f"  grava no ESTOQUE ......... {ok_grava}" + ("" if ok_grava else f"  ({detalhe})"))

    if certo and ok_grava:
        print("\nCorreção aplicada. A validação de código de barras continua valendo,")
        print("e agora dá para gravar no ESTOQUE e usar o checkbox da tela.")
        return 0
    print("\nAlgo não fechou. Restaure o backup e revise antes de gravar qualquer coisa.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
