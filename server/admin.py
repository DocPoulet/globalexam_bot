"""CLI administrateur (depuis le serveur uniquement, jamais dans le bot)."""
import argparse
import secrets
import time
import uuid

from .settings import Settings
from .store import PostgresStore, key_digest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gestion de l'API communautaire")
    subs = parser.add_subparsers(dest="command", required=True)
    init = subs.add_parser("init-db", help="Créer les tables si absentes")
    init.add_argument(
        "--wait-seconds", type=int, default=0,
        help="Attendre le démarrage de PostgreSQL, maximum 120 secondes",
    )
    create = subs.add_parser("create-client", help="Créer une identité avec clé propre")
    create.add_argument("--label", required=True, help="Nom public administratif (80 caractères max)")
    revoke = subs.add_parser("revoke-client", help="Désactiver immédiatement une clé")
    revoke.add_argument("--id", required=True, help="UUID du client")
    args = parser.parse_args(argv)
    store = PostgresStore(Settings.from_env().database_url)

    if args.command == "init-db":
        if not 0 <= args.wait_seconds <= 120:
            parser.error("--wait-seconds doit être entre 0 et 120")

        # Railway peut démarrer l'API juste après le provisionnement SQL.
        # Les erreurs SQL de schéma ne doivent pas être masquées ou retentées.
        import psycopg
        deadline = time.monotonic() + args.wait_seconds
        while True:
            try:
                store.init_db()
                break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(min(2, max(0, deadline - time.monotonic())))
        print("Tables PostgreSQL prêtes.")
    elif args.command == "create-client":
        if not args.label or len(args.label) > 80:
            parser.error("--label doit contenir de 1 à 80 caractères")
        key = "gec1_" + secrets.token_urlsafe(32)
        uid = uuid.uuid4()
        with store._connect() as conn:
            conn.execute(
                """INSERT INTO community_clients (id, label, api_key_sha256)
                   VALUES (%s, %s, %s)""", (uid, args.label, key_digest(key))
            )
        print(f"Client ID: {uid}")
        print(f"API key (affichée UNE seule fois): {key}")
        print("Conserver dans un coffre à secrets; ne pas la mettre dans config.json.")
    elif args.command == "revoke-client":
        uid = uuid.UUID(args.id)
        with store._connect() as conn:
            cur = conn.execute(
                "UPDATE community_clients SET revoked_at=now() WHERE id=%s AND revoked_at IS NULL", (uid,)
            )
            if cur.rowcount:
                # La clé révoquée ne doit plus influer sur un consensus.
                conn.execute("DELETE FROM community_contributions WHERE client_id=%s", (uid,))
        print("Client désactivé; contributions supprimées." if cur.rowcount else "Aucun client actif avec cet ID.")


if __name__ == "__main__":
    main()
