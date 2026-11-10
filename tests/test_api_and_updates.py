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
