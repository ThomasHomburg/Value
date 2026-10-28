"""Import-Test: `import app` muss ohne ImportError laufen.

Sichert alle Imports aus valuation/ und scoring/ ab (Regression: app.py
referenzierte sensitivity_mos_base, das nicht im Paket-Export war).
"""

import importlib


def test_import_app_ohne_fehler():
    mod = importlib.import_module("app")
    assert hasattr(mod, "page_ranking")
    assert hasattr(mod, "page_scorecard")
    assert hasattr(mod, "dcf_section")


def test_valuation_paket_export_vollstaendig():
    import valuation
    for name in ("DcfResult", "DcfScenario", "compute_dcf", "is_buy_candidate",
                 "sensitivity_mos_base"):
        assert hasattr(valuation, name), f"valuation.{name} fehlt"


def test_scoring_paket_imports():
    from scoring.criteria import CRITERIA, compute_criteria
    from scoring.pipeline import evaluate_all, evaluate_ticker, rank_rows
    from scoring.score import interpolate, score_ticker
    assert "mos_base" in CRITERIA
    assert callable(compute_criteria)
    assert callable(evaluate_all) and callable(evaluate_ticker) and callable(rank_rows)
    assert callable(score_ticker) and callable(interpolate)


def test_app_importiert_sensitivity_aus_valuation():
    """app.dcf_section nutzt valuation.dcf.sensitivity_mos_base (gleiche Funktion)."""
    import app
    from valuation.dcf import sensitivity_mos_base
    import inspect
    src = inspect.getsource(app.dcf_section)
    assert "sensitivity_mos_base" in src
    assert app.rank_rows is not None
