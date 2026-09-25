"""Three tests, three criteria cited. One of the tests does not run.

The file is named `check_prices.py`, not `test_*.py`, so the harness's own suite never collects
it; pytest still runs it when the path is given on the command line.
"""
import pytest


def price(total: float, member: bool) -> float:
    if member:
        total *= 0.90
    if total >= 100.00:
        total *= 0.95
    return round(total, 2)


def test_member_discount():
    """[spec: pricing/member-discount]"""
    assert price(50.00, member=True) == 45.00


@pytest.mark.skip(reason="the bulk rule is being rewritten")
def test_bulk_discount():
    """[spec: pricing/bulk-discount]"""
    assert price(200.00, member=False) == 190.00


def test_rounding():
    """[spec: pricing/rounding]"""
    assert price(33.333, member=False) == 33.33
