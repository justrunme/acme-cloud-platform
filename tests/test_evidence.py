from tools import check_policies, check_restore
from tools.common import ROOT
from tools.evidence import validate_all


def test_all_packages_valid():
    report = validate_all(ROOT)
    assert len(report) == 4
    assert all(r["ok"] for r in report), report


def test_policies_and_fixtures():
    r = check_policies.run(ROOT)
    assert r["summary"]["passed"], r


def test_restore_decisions():
    r = check_restore.run(ROOT)
    assert r["summary"]["passed"], r
