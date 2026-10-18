import pytest

from tools import negative_checks


@pytest.mark.parametrize("name", [c[0] for c in negative_checks.CHECKS])
def test_mutation_is_rejected(name):
    row = negative_checks.run_one(name)
    assert row["pass"], f"{name} was accepted: {row}"
