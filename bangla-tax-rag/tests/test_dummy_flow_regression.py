from __future__ import annotations

from scripts.run_dummy_flow_regression import run


def test_dummy_flow_regression_suite() -> None:
    assert run() == 0
