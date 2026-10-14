"""Commandes locales de préparation (aucune synchronisation réseau)."""
import argparse
import json
import sqlite3
from pathlib import Path

from community_preview import build_preview, export_local_preview
from community_protocol import validate_envelope

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="V0.10.13 : aperçu de synchronisation, 100 % local")
    parser.add_argument("command", choices=("status", "export", "validate"))
    parser.add_argument("--db", default=str(ROOT / "data" / "knowledge.sqlite3"))
    parser.add_argument("--output", default=str(ROOT / "data" / "community_preview.json"))
    parser.add_argument("--input", help="Fichier JSON à valider (pour la commande validate)")
    parser.add_argument("--confirm-review", action="store_true",
                        help="Confirme la revue du fichier et des droits avant export local")
    args = parser.parse_args(argv)

    if args.command == "validate":
        if not args.input:
            parser.error("validate nécessite --input FICHIER.json")
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        validate_envelope(data)
        print(f"Contrat valide : {len(data['records'])} contribution(s). Aucun envoi réseau.")
        return 0

    envelope, counts = build_preview(args.db)
    print("=== Aperçu communautaire V1 (hors ligne) ===")
    print(f"Contributions admissibles : {len(envelope['records'])}")
    for reason, count in counts.items():
        if reason != "eligible":
            print(f"Exclues [{reason}] : {count}")
    print("Aucun texte de question ou solution et aucune URL exportés.")
    print("ATTENTION : les empreintes SHA-256 ne garantissent PAS l'anonymat.")
    print("Connexion au serveur : désactivée.")
    if args.command == "export":
        path, _ = export_local_preview(args.db, args.output, confirm_review=args.confirm_review)
        print(f"Aperçu local créé : {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, sqlite3.DatabaseError, ValueError, PermissionError) as exc:  # noqa: F821
        print(f"Erreur : {exc}")
        raise SystemExit(1)
