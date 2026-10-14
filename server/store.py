"""Accès PostgreSQL : paramètres SQL liés, transactions et quotas en base."""
import hashlib
import json
from pathlib import Path

from .logic import ClientConflict, QuotaExceeded, compute_consensus


def key_digest(raw_key):
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class PostgresStore:
    def __init__(self, database_url):
        self.database_url = database_url

    def _connect(self):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL manquant")
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.database_url, connect_timeout=5, row_factory=dict_row)

    def ready(self):
        """Indique si PostgreSQL répond ET si le schéma attendu existe.

        Ne divulgue aucune configuration dans la réponse de santé.
        """
        with self._connect() as conn:
            row = conn.execute(
                """SELECT to_regclass('public.community_clients') IS NOT NULL
                            AND to_regclass('public.community_contributions') IS NOT NULL
                            AND to_regclass('public.community_api_usage') IS NOT NULL
                            AS ready"""
            ).fetchone()
            return bool(row["ready"])

    def init_db(self):
        sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
        with self._connect() as conn:
            # La migration reste distincte du service HTTP. Sérialisation
            # des lancements concurrents (pre-deploy Railway, compose, etc.).
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (10101415,))
            # Schéma statique versionné ; exécuter chaque instruction séparément
            # pour rester compatible avec le protocole préparé de psycopg 3.
            for statement in sql.split(";"):
                if statement.strip():
                    conn.execute(statement)

    def authenticate(self, raw_key):
        if not raw_key or len(raw_key) > 160 or not raw_key.startswith("gec1_"):
            return None
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, label FROM community_clients
                   WHERE api_key_sha256 = %s AND revoked_at IS NULL""",
                (key_digest(raw_key),),
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def _use_quota(conn, client_id, action, increment, maximum):
        # Sérialise les demandes concurrentes du même client : pas de bypass
        # du quota via plusieurs requêtes en parallèle.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(client_id),))
        used = conn.execute(
            """SELECT used_count FROM community_api_usage
               WHERE client_id=%s AND usage_day=CURRENT_DATE AND action=%s""",
            (client_id, action),
        ).fetchone()
        if (used["used_count"] if used else 0) + increment > maximum:
            raise QuotaExceeded("daily_quota_exceeded")
        conn.execute(
            """INSERT INTO community_api_usage(client_id, usage_day, action, used_count)
               VALUES (%s, CURRENT_DATE, %s, %s)
               ON CONFLICT (client_id, usage_day, action)
               DO UPDATE SET used_count = community_api_usage.used_count + EXCLUDED.used_count""",
            (client_id, action, increment),
        )

    def submit(self, client_id, records, daily_limit):
        from psycopg.types.json import Jsonb
        # Transaction atomique : si une contribution est incohérente, aucune
        # entrée du lot n'est ajoutée.
        with self._connect() as conn:
            self._use_quota(conn, client_id, "write", len(records), daily_limit)
            inserted = 0
            duplicates = 0
            for record in records:
                question_fp = record["question_fingerprint"]
                current = conn.execute(
                    """SELECT record_fingerprint FROM community_contributions
                       WHERE client_id=%s AND question_fingerprint=%s FOR UPDATE""",
                    (client_id, question_fp),
                ).fetchone()
                if current:
                    if current["record_fingerprint"] != record["record_fingerprint"]:
                        raise ClientConflict("one_vote_per_question; contradictory change rejected")
                    duplicates += 1
                    continue
                conn.execute(
                    """INSERT INTO community_contributions(
                           client_id, question_fingerprint, record_fingerprint,
                           exercise_type, evidence_category, answer
                       ) VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (client_id, question_fingerprint) DO NOTHING""",
                    (
                        client_id, question_fp, record["record_fingerprint"],
                        record["exercise_type"], record["evidence_category"],
                        Jsonb(record["answer"]),
                    ),
                )
                # Same-client writes are serialized, so if no existing row,
                # the write is unique for this client/question.
                inserted += 1
            return {"accepted": inserted, "duplicates": duplicates}

    def lookup(self, client_id, question_fp, min_confirmations, daily_limit):
        with self._connect() as conn:
            self._use_quota(conn, client_id, "read", 1, daily_limit)
            groups = conn.execute(
                """SELECT v.answer, COUNT(DISTINCT v.client_id) AS supporters
                   FROM community_contributions AS v
                   JOIN community_clients AS c ON c.id=v.client_id
                   WHERE question_fingerprint=%s AND c.revoked_at IS NULL
                   GROUP BY v.answer""",
                (question_fp,),
            ).fetchall()
        result = compute_consensus(
            [(row["answer"], row["supporters"]) for row in groups],
            min_confirmations=min_confirmations,
        )
        return result

    def stats(self, client_id):
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS total FROM community_contributions
                   WHERE client_id=%s""", (client_id,)
            ).fetchone()
        return {"submitted_questions": row["total"]}
