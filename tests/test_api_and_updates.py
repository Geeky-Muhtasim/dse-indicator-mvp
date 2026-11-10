"""Backend and daily-update guarantees."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "api"))

from dse_signal.dse_live import merge_adjusted  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import index
    return TestClient(index.app)


def test_pure_python_treeshap_matches_lightgbm():
    """The API's explanation must equal LightGBM's own TreeSHAP and prediction."""
    lgb = pytest.importorskip("lightgbm")
    import index
    feats, _ = index.model()
    booster = lgb.Booster(model_file=str(ROOT / "data/model/model_lgbm.txt"))
    values = json.loads((ROOT / "data/app/features.json").read_text())["values"]
    syms = list(values)[:10]
    X = np.array([[values[s][f] for f in feats] for s in syms])
    ref = booster.predict(X, pred_contrib=True)
    pred = booster.predict(X)
    for i, s in enumerate(syms):
        ex = index.explain(values[s])
        phi = {c["feature"]: c["shap"] for c in ex["contributions"]}
        assert np.allclose([phi[f] for f in feats], ref[i, :-1], atol=1e-9)
        assert ex["base"] == pytest.approx(ref[i, -1], abs=1e-9)
        assert ex["score"] == pytest.approx(pred[i], abs=1e-9)
        assert ex["base"] + sum(phi.values()) == pytest.approx(ex["score"], abs=1e-9)


def test_routes(client):
    assert client.get("/api/health").json()["status"] == "ok"
    rows = client.get("/api/signals?signal=buy").json()["rows"]
    assert rows and all(r["signal"] == "BUY" for r in rows)
    sym = rows[0]["symbol"]
    stock = client.get(f"/api/stock/{sym}").json()
    assert stock["explanation"]["score"] == pytest.approx(rows[0]["score"], abs=1e-4)
    r = client.post("/api/score", json={"symbol": sym, "overrides": {"rsi_14": 50}}).json()
    assert r["placement"]["signal"] in {"BUY", "HOLD", "AVOID"}
    assert client.get("/api/stock/NOT_A_TICKER").status_code == 404
    assert client.post("/api/score", json={"symbol": sym, "overrides": {"nope": 1}}).status_code == 422


def _hist(closes, sym="ABC", start="2026-11-01"):
    d = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Symbol": sym, "Date": d, "Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": 1000.0})


def test_merge_without_corporate_action():
    hist = _hist([100.0, 101.0, 102.0])
    new = pd.DataFrame({"Symbol": ["ABC"], "Date": [pd.Timestamp("2026-11-10")], "Open": [102.5], "High": [103.0],
                        "Low": [101.5], "Close": [103.0], "Volume": [900.0], "YCP": [102.0]})
    out, ev = merge_adjusted(hist, new)
    assert ev == []
    assert out["Close"].tolist() == [100.0, 101.0, 102.0, 103.0]


def test_merge_back_adjusts_bonus_issue():
    """A 20% bonus: DSE reports YCP = 102 / 1.2 = 85. History must be rescaled by 85/102."""
    hist = _hist([100.0, 101.0, 102.0])
    new = pd.DataFrame({"Symbol": ["ABC"], "Date": [pd.Timestamp("2026-11-10")], "Open": [85.0], "High": [86.0],
                        "Low": [84.0], "Close": [86.0], "Volume": [1200.0], "YCP": [85.0]})
    out, ev = merge_adjusted(hist, new)
    f = 85.0 / 102.0
    assert len(ev) == 1 and ev[0]["factor"] == pytest.approx(f, rel=1e-6)
    assert out["Close"].iloc[:3].tolist() == pytest.approx([100 * f, 101 * f, 102 * f], rel=1e-4)
    assert out["Volume"].iloc[0] == pytest.approx(1000 / f, abs=1)
    # The day-over-day move across the ex-date is now the real +1.2%, not a fake -17% crash.
    assert out["Close"].iloc[3] / out["Close"].iloc[2] - 1 == pytest.approx(86 / 85 - 1, rel=1e-3)


def test_vectorized_backfill_matches_daily_merge():
    """adjust_history over a whole panel equals applying merge_adjusted one day at a time."""
    from dse_signal.dse_live import adjust_history
    d = pd.bdate_range("2026-01-05", periods=6)
    raw = pd.DataFrame({
        "Symbol": ["A"] * 6 + ["B"] * 6, "Date": list(d) * 2,
        "Close": [100, 102, 85, 86, 87, 70, 50, 51, 52, 53, 54, 55.0],
        # A: 20% bonus before day 3 (YCP 85 = 102/1.2), and another before day 6 (YCP 72.5 vs 87)
        "YCP": [99, 100, 85, 85, 86, 72.5, 49, 50, 51, 52, 53, 54.0], "Volume": 1000.0,
    })
    raw["Open"] = raw["High"] = raw["Low"] = raw["Close"]
    adj, ev = adjust_history(raw)
    seed = raw[raw["Date"] == d[0]][["Symbol", "Date", "Open", "High", "Low", "Close", "Volume"]]
    step, _ = merge_adjusted(seed, raw[raw["Date"] > d[0]])
    a = adj.sort_values(["Symbol", "Date"])["Close"].to_numpy()
    b = step.sort_values(["Symbol", "Date"])["Close"].to_numpy()
    assert np.allclose(a, b, rtol=1e-6)
    assert len(ev) == 2 and set(ev["symbol"]) == {"A"}


def test_glitch_ycp_is_not_an_adjustment():
    from dse_signal.dse_live import adjust_history
    d = pd.bdate_range("2026-01-05", periods=3)
    raw = pd.DataFrame({"Symbol": "A", "Date": d, "Close": [100, 101, 102.0], "YCP": [99, 0, 101.0], "Volume": 1.0})
    raw["Open"] = raw["High"] = raw["Low"] = raw["Close"]
    adj, ev = adjust_history(raw)
    assert len(ev) == 0 and adj["Close"].tolist() == [100, 101, 102]


def test_gap_rule_catches_bonus_but_not_limit_down():
    from dse_signal.dse_live import gap_factor
    # 25% bonus: yesterday 25.2, today trades 19.9 to 20.6 (whole day far below the old price)
    assert gap_factor(25.2, 19.9, 20.6, 19.7) == pytest.approx(1 / 1.25)
    # genuine crash locked at the 10% limit (high == low): not an adjustment
    assert gap_factor(110.0, 99.0, 99.0, 99.0) == 1.0
    # ordinary bad day: high only 3% below
    assert gap_factor(100.0, 97.0, 97.5, 92.0) == 1.0


def test_reference_factors_recover_exact_bonus():
    from dse_signal.dse_live import reference_factors
    d = pd.bdate_range("2026-10-12", periods=4)
    raw = pd.DataFrame({"Symbol": "X", "Date": d, "Close": [194.5, 195.0, 170.3, 171.0]})
    ref = raw.assign(Close=[194.5 / 1.15, 195.0 / 1.15, 170.3, 171.0])
    rf = reference_factors(raw, ref)
    assert len(rf) == 1 and rf["Date"].iloc[0] == d[2]
    assert rf["factor"].iloc[0] == pytest.approx(1 / 1.15)


def test_not_rated_stocks_are_listed_but_not_scored(client):
    rows = client.get("/api/signals").json()["rows"]
    nr = [r for r in rows if r["signal"] == "NR"]
    if not nr:
        pytest.skip("every listed stock is rated today")
    assert all(r["reason"] in {"illiquid", "new", "not_traded", "incomplete"} for r in nr)
    stock = client.get(f"/api/stock/{nr[0]['symbol']}").json()
    assert stock["explanation"] is None and stock["signal"]["signal"] == "NR"
    assert client.post("/api/score", json={"symbol": nr[0]["symbol"], "overrides": {}}).status_code == 404
    # placement ignores unrated rows
    rated = next(r for r in rows if r["signal"] != "NR")
    assert client.post("/api/score", json={"symbol": rated["symbol"], "overrides": {}}).status_code == 200
