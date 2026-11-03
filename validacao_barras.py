"""Liga e desliga a validação de código de barras do ESTOQUE.

No Firebird não se desativa uma função: quem roda na gravação é o trigger
``TR_ESTOQUE_BARRAS`` (BEFORE INSERT OR UPDATE), que chama
``FN_VALIDA_BARCODE``. É esse trigger que este módulo ativa e desativa.

Motivo de existir: ``FN_VALIDA_BARCODE`` usa ``MOD``, que no banco está
declarada como UDF legada de ``ib_udf``. O Firebird 5 não carrega UDF por
padrão e não distribui mais essa biblioteca, então o trigger derruba qualquer
UPDATE no ESTOQUE com "function MOD is not defined". Desligar a validação
libera a gravação; a correção definitiva é remover a declaração da UDF e
recompilar a função, que passa a usar o ``MOD`` nativo do Firebird.
"""

from __future__ import annotations

from db import conectar

TRIGGER = "TR_ESTOQUE_BARRAS"
FUNCAO = "FN_VALIDA_BARCODE"


def _ler(cur) -> int | None:
    cur.execute(
        """
        SELECT COALESCE(RDB$TRIGGER_INACTIVE, 0)
        FROM RDB$TRIGGERS
        WHERE TRIM(RDB$TRIGGER_NAME) = ?
        """,
        (TRIGGER,),
    )
    row = cur.fetchone()
    return None if row is None else int(row[0])


def status() -> dict:
    conn = conectar()
    try:
        inativo = _ler(conn.cursor())
    finally:
        conn.close()
    if inativo is None:
        return {
            "ok": True,
            "existe": False,
            "ativo": False,
            "trigger": TRIGGER,
            "funcao": FUNCAO,
            "situacao": f"{TRIGGER} não existe neste banco.",
        }
    ativo = inativo == 0
    return {
        "ok": True,
        "existe": True,
        "ativo": ativo,
        "trigger": TRIGGER,
        "funcao": FUNCAO,
        "situacao": (
            f"Validação ligada: {FUNCAO} roda a cada gravação."
            if ativo
            else f"Validação desligada: {FUNCAO} não roda."
        ),
    }


AJUDA_UDF = (
    f"O Firebird revalida o corpo do trigger ao alterá-lo, e {FUNCAO} usa MOD, "
    "declarada no banco como UDF legada de ib_udf que o Firebird 5 não carrega. "
    "Enquanto essa declaração existir não dá para ligar nem desligar a validação, "
    "nem gravar no ESTOQUE. A saída é recompilar a função sem depender da UDF."
)


def definir(ativo: bool) -> dict:
    conn = conectar()
    try:
        cur = conn.cursor()
        if _ler(cur) is None:
            raise ValueError(f"{TRIGGER} não existe neste banco.")
        try:
            cur.execute(f"ALTER TRIGGER {TRIGGER} {'ACTIVE' if ativo else 'INACTIVE'}")
            conn.commit()
        except Exception as e:
            conn.rollback()
            if "MOD" in str(e) or "BLR" in str(e):
                raise RuntimeError(f"{e}\n\n{AJUDA_UDF}") from e
            raise
    finally:
        conn.close()

    novo = status()
    if novo["ativo"] != ativo:
        raise RuntimeError(f"O banco não aceitou alterar {TRIGGER}.")
    novo["alterado"] = True
    return novo
