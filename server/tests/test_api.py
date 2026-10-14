"""API contract tests, fully offline: no GlobalExam, Docker or Postgres access."""
import hashlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.app import create_app
from server.logic import ClientConflict, QuotaExceeded, compute_consensus
from server.settings import Settings
from server.shared_protocol import validate_record
from server.store import key_digest


class FakeStore:
    def __init__(self):
        self.records = {}
        self.tokens = {"gec1_" + "x" * 43: "client-a"}
        self.lookups = 0

    def ready(self):
        return True

    def authenticate(self, key):
        if key in self.tokens:
            return {"id": self.tokens[key], "label": "test"}
        return None

    def stats(self, client_id):
        return {"submitted_questions": len(self.records)}

    def submit(self, client_id, records, daily_limit):
        if len(records) > daily_limit:
            raise QuotaExceeded("quota")
        inserted = 0
        duplicates = 0
        for record in records:
            q = (client_id, record["question_fingerprint"])
            old = self.records.get(q)
            if old and old["record_fingerprint"] != record["record_fingerprint"]:
                raise ClientConflict("different answer")
            if old:
                duplicates += 1
            else:
                inserted += 1
                self.records[q] = record
        return {"accepted": inserted, "duplicates": duplicates}

    def lookup(self, client_id, q, min_confirmations, daily_limit):
        self.lookups += 1
        choices = {}
        for (owner, question), record in self.records.items():
            if question != q:
                continue
            fp = record["record_fingerprint"]
            if fp not in choices:
                choices[fp] = (record["answer"], 0)
            answer, n = choices[fp]
            choices[fp] = answer, n + 1
        return compute_consensus(list(choices.values()), min_confirmations)


KEY = "gec1_" + "x" * 43
HEADERS = {"X-API-Key": KEY}


def hash_value(domain, value):
    from server.shared_protocol import SRC_DIR
    from community_protocol import _digest
    return _digest(domain, value)


def sample_record():
    from community_protocol import create_record
    packet = {
        "exercise_type": "qcm_single", "html_language": "en",
        "instruction": "Choose the correct animal",
        "context": "The animal barks.",
        "choices": [
            {"index": 0, "text": "Cat"},
            {"index": 1, "text": "Dog"},
        ],
    }
    return create_record(packet, {"kind":"choice_indices", "indices":[1]}, "dom_correct_markers")


def make_client(writes=False, min_votes=3):
    fake = FakeStore()
    cfg = Settings(database_url="", writes_enabled=writes,
                   min_confirmations=min_votes, read_limit_day=50,
                   write_limit_day=200)
    return TestClient(create_app(store=fake, settings=cfg)), fake


def test_health_and_auth():
    client, _ = make_client()
    assert client.get('/healthz').json() == {"status": "ready", "writes_enabled": False}
    assert client.get('/v1/status').status_code == 401
    assert client.get('/v1/status', headers={"X-API-Key":"bad"}).status_code == 401
    assert client.get('/v1/status', headers=HEADERS).json()["submitted_questions"] == 0


def test_upload_blocked_by_default():
    client, fake = make_client()
    res=client.post('/v1/contributions',headers=HEADERS,json={
        "schema_version":"1.0", "platform":"globalexam", "records":[sample_record()]})
    assert res.status_code == 403
    assert not fake.records


def test_upload_and_idempotence():
    client, fake = make_client(writes=True)
    body={"schema_version":"1.0", "platform":"globalexam", "records":[sample_record()]}
    assert client.post('/v1/contributions',headers=HEADERS,json=body).json() == {
        "status":"received_unverified", "accepted":1, "duplicates":0}
    assert client.post('/v1/contributions',headers=HEADERS,json=body).json()["duplicates"]==1
    lookup=client.get('/v1/answers/'+body['records'][0]['question_fingerprint'],headers=HEADERS).json()
    assert lookup['status']=='pending'
    assert 'answer' not in lookup


def test_reject_bogus_and_preview():
    client,fake = make_client(writes=True)
    r = sample_record()
    r['url'] = 'https://example.com/private'
    body={"schema_version":"1.0", "platform":"globalexam", "records":[r]}
    assert client.post('/v1/contributions',headers=HEADERS,json=body).status_code==422
    r.pop('url')
    r['record_fingerprint']='sha256:'+'0'*64
    assert client.post('/v1/contributions',headers=HEADERS,json=body).status_code==422
    body['records']=[sample_record()]
    body['network_upload']=False
    body['privacy']='hashed_metadata_preview'
    assert client.post('/v1/contributions',headers=HEADERS,json=body).status_code==422
    assert not fake.records


def test_reject_duplicate_batch_and_invalid_fingerprint():
    client,fake = make_client(writes=True)
    record=sample_record()
    body={"schema_version":"1.0", "platform":"globalexam", "records":[record,record]}
    assert client.post('/v1/contributions',headers=HEADERS,json=body).status_code == 422
    assert client.get('/v1/answers/wrong',headers=HEADERS).status_code == 422
    assert not fake.records


def test_conflict_consensus_quota():
    ans = {'kind':'choice_keys','values':['sha256:'+'1'*64]}
    assert compute_consensus([],3)['status']=='not_found'
    assert compute_consensus([(ans,2)],3)['status']=='pending'
    assert compute_consensus([(ans,3)],3)['status']=='consensus'
    assert compute_consensus([(ans,9),({'kind':'choice_keys','values':['sha256:'+'2'*64]},1)],3)['status']=='disputed'
    client,fake = make_client(writes=True)
    record=sample_record()
    body={"schema_version":"1.0", "platform":"globalexam", "records":[record]}
    assert client.post('/v1/contributions',headers=HEADERS,json=body).status_code==200
    new = dict(record)
    new['answer']={'kind':'choice_keys','values':['sha256:'+'1'*64]}
    # use shared fingerprint algorithm
    from community_protocol import _digest
    new['record_fingerprint'] = _digest('record',{k:v for k,v in new.items() if k!='record_fingerprint'})
    validate_record(new)
    body['records']=[new]
    assert client.post('/v1/contributions',headers=HEADERS,json=body).status_code==409
    assert len(fake.records)==1


def test_body_limit():
    client, fake = make_client(writes=True)
    result=client.post('/v1/contributions',headers=HEADERS,
                       content=b'x'*65537)
    assert result.status_code==413


def test_key_hash_not_plaintext():
    assert key_digest(KEY)==hashlib.sha256(KEY.encode()).hexdigest()
    assert KEY not in key_digest(KEY)


def test_readiness_unavailable_fails_closed():
    client, fake = make_client()
    fake.ready = lambda: False
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"detail": "database_unavailable"}
    fake.ready = lambda: (_ for _ in ()).throw(ConnectionError("private-password"))
    response = client.get("/healthz")
    assert response.status_code == 503
    assert "private-password" not in response.text


def test_healthcheck_needs_no_api_key_but_status_does():
    client, _ = make_client()
    assert client.get("/healthz").status_code == 200
    assert client.get("/v1/status").status_code == 401
