-- V0.10.14. Aucune question/correction/URL en clair n'est stockée.
CREATE TABLE IF NOT EXISTS community_clients (
    id UUID PRIMARY KEY,
    label VARCHAR(80) NOT NULL,
    api_key_sha256 CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS community_contributions (
    id BIGSERIAL PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES community_clients(id) ON DELETE CASCADE,
    question_fingerprint VARCHAR(71) NOT NULL,
    record_fingerprint VARCHAR(71) NOT NULL,
    exercise_type VARCHAR(32) NOT NULL,
    evidence_category VARCHAR(40) NOT NULL,
    answer JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT one_vote_per_client_question UNIQUE (client_id, question_fingerprint),
    CONSTRAINT unique_record_per_client UNIQUE (client_id, record_fingerprint)
);
CREATE INDEX IF NOT EXISTS community_contributions_lookup
    ON community_contributions (question_fingerprint);

CREATE TABLE IF NOT EXISTS community_api_usage (
    client_id UUID NOT NULL REFERENCES community_clients(id) ON DELETE CASCADE,
    usage_day DATE NOT NULL DEFAULT CURRENT_DATE,
    action VARCHAR(16) NOT NULL CHECK (action IN ('read', 'write')),
    used_count INT NOT NULL DEFAULT 0 CHECK (used_count >= 0),
    PRIMARY KEY (client_id, usage_day, action)
);
