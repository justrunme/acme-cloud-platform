"""PreSync gate against a local evidence store (no cluster needed)."""
import threading
from http.server import ThreadingHTTPServer

import pytest

from tools import evidence_store, presync_gate


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence_store, "RECORDS", tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), evidence_store.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path
    srv.shutdown()


def gate(url, change, package=None):
    rec = presync_gate.decide(change, url, package or f"evidence/{change}.json", 3)
    return presync_gate.retain(rec, url, 3)


@pytest.mark.parametrize("change,decision,reason", [
    ("CHG-0042", "BLOCK", "verdict_block"),
    ("CHG-0043", "REQUIRE_APPROVAL", "approval_required"),
    ("CHG-0044", "ALLOW", "verdict_allow"),
    ("CHG-0045", "BLOCK", "verdict_block"),
])
def test_recorded_verdicts(store, change, decision, reason):
    url, records = store
    rec = gate(url, change)
    assert (rec["decision"], rec["reason"]) == (decision, reason)
    assert rec["record"] and (records / rec["record"].split("/", 1)[1]).is_file()


def test_edited_package_is_blocked(store):
    rec = gate(store[0], "CHG-0042", "fixtures/CHG-0042-edited-to-allow.json")
    assert (rec["decision"], rec["reason"]) == ("BLOCK", "evidence_invalid")
    assert any("envelopeSha256" in e for e in rec["errors"])


def test_store_down_blocks_an_allow_package():
    rec = gate("http://127.0.0.1:9", "CHG-0044")
    assert (rec["decision"], rec["reason"]) == ("BLOCK", "evidence_store_unavailable")


def test_allow_that_cannot_be_retained_is_blocked(store, monkeypatch):
    url, _ = store
    rec = presync_gate.decide("CHG-0044", url, "evidence/CHG-0044.json", 3)
    assert rec["decision"] == "ALLOW"
    rec = presync_gate.retain(rec, "http://127.0.0.1:9", 3)
    assert (rec["decision"], rec["reason"]) == ("BLOCK", "evidence_not_retained")
