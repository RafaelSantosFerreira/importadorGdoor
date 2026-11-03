"""
Importa CSV para ESTOQUE usando o de-para salvo em mapeamento_estoque.json.
Usa a mesma lógica da tela de importação (importar_service.importar).

Uso:
  python importar_estoque_csv.py                 # simulação (ROLLBACK no fim)
  python importar_estoque_csv.py --apply         # grava (só se não houver erros)
  python importar_estoque_csv.py --apply --mode update --cadastro
"""

from __future__ import annotations

import argparse

from importar_service import importar


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa CSV → ESTOQUE via de-para")
    parser.add_argument("--apply", action="store_true", help="grava no banco")
    parser.add_argument("--dry-run", action="store_true", help="(padrão) simula")
    parser.add_argument("--mode", choices=("insert", "update", "upsert"), default="upsert")
    parser.add_argument("--sem-preco", action="store_true", help="não atualiza preços")
    parser.add_argument("--sem-estoque", action="store_true", help="não atualiza quantidades")
    parser.add_argument(
        "--cadastro", action="store_true", help="atualiza demais campos mapeados dos existentes"
    )
    args = parser.parse_args()
    dry_run = not args.apply or args.dry_run
    so_insert = args.mode == "insert"

    r = importar(
        atualizar_preco=not so_insert and not args.sem_preco,
        atualizar_estoque=not so_insert and not args.sem_estoque,
        atualizar_cadastro=not so_insert and args.cadastro,
        inserir_novos=args.mode != "update",
        dry_run=dry_run,
    )

    for linha in r["log"]:
        print(linha)
    print("\nResumo:")
    print(f"  Campos no UPDATE: {', '.join(r['campos_update']) or 'nenhum'}")
    print(f"  Inserir:   {r['inseridos']}")
    print(f"  Atualizar: {r['atualizados']}")
    print(f"  Pular:     {r['pulados']}")
    print(f"  Erros:     {r['erros']}")
    print(f"\n{r['situacao']}")
    if dry_run:
        print("Use --apply para gravar.")


if __name__ == "__main__":
    main()
