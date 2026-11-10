"""DSE Signal API (FastAPI, deployed as a Vercel Python function).

Serves the daily signals produced by the pipeline and scores stocks live.
Live scoring and explanations use the exported LightGBM trees with a pure-Python
TreeSHAP (Lundberg et al., 2018), so the function needs no numpy or lightgbm.
"""
from __future__ import annotations

import json
import math
import time
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATA = Path(__file__).resolve().parent.parent / "data" / "app"

app = FastAPI(title="DSE Signal API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


@lru_cache(maxsize=None)
def load(name: str):
    path = DATA / f"{name}.json"
    if not path.exists():
        raise HTTPException(503, f"{name}.json has not been generated yet")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- tree model
class Tree:
    __slots__ = ("f", "t", "l", "r", "v", "c", "d")

    def __init__(self, raw: dict):
        self.f, self.t, self.l, self.r = raw["f"], raw["t"], raw["l"], raw["r"]
        self.v, self.c, self.d = raw["v"], raw["c"], raw["d"]

    def predict(self, x) -> float:
        i = 0
        while self.f[i] >= 0:
            xv = x[self.f[i]]
            go_left = (self.d[i] == 1) if xv is None or (isinstance(xv, float) and math.isnan(xv)) else xv <= self.t[i]
            i = self.l[i] if go_left else self.r[i]
        return self.v[i]

    def expected(self) -> float:
        """Cover-weighted mean of leaf values: this tree's contribution to the base value."""
        tot = sum(c for f, c in zip(self.f, self.c) if f < 0)
        return sum(v * c for f, v, c in zip(self.f, self.v, self.c) if f < 0) / tot if tot else 0.0


@lru_cache(maxsize=1)
def model():
    m = load("model")
    return m["features"], [Tree(t) for t in m["trees"]]


def _extend(m, pz, po, pi):
    m = [list(e) for e in m]  # (feature, zero_frac, one_frac, weight)
    l = len(m)
    m.append([pi, pz, po, 1.0 if l == 0 else 0.0])
    for i in range(l - 1, -1, -1):
        m[i + 1][3] += po * m[i][3] * (i + 1) / (l + 1)
        m[i][3] = pz * m[i][3] * (l - i) / (l + 1)
    return m


def _unwind(m, i):
    L = len(m)
    n = m[L - 1][3]
    w = [e[3] for e in m[:L - 1]]
    _, zi, oi, _ = m[i]
    for j in range(L - 2, -1, -1):
        if oi != 0:
            t = w[j]
            w[j] = n * L / ((j + 1) * oi)
            n = t - w[j] * zi * (L - (j + 1)) / L
        else:
            w[j] = w[j] * L / (zi * (L - (j + 1)))
    out = [list(e) for e in m[:L - 1]]
    for j in range(L - 1):
        out[j][3] = w[j]
    for j in range(i, L - 1):
        out[j][0], out[j][1], out[j][2] = m[j + 1][0], m[j + 1][1], m[j + 1][2]
    return out


def _unwound_sum(m, i):
    return sum(e[3] for e in _unwind(m, i))


def tree_shap(tree: Tree, x, phi) -> None:
    """Path-dependent TreeSHAP, Algorithm 2 of Lundberg, Erion and Lee (2018)."""
    def recurse(j, m, pz, po, pi):
        m = _extend(m, pz, po, pi)
        if tree.f[j] < 0:
            for i in range(1, len(m)):
                phi[m[i][0]] += _unwound_sum(m, i) * (m[i][2] - m[i][1]) * tree.v[j]
            return
        f = tree.f[j]
        xv = x[f]
        left = (tree.d[j] == 1) if xv is None else xv <= tree.t[j]
        hot, cold = (tree.l[j], tree.r[j]) if left else (tree.r[j], tree.l[j])
        iz = io = 1.0
        k = next((k for k in range(1, len(m)) if m[k][0] == f), None)
        if k is not None:
            iz, io = m[k][1], m[k][2]
            m = _unwind(m, k)
        rj = tree.c[j]
        recurse(hot, m, iz * tree.c[hot] / rj, io, f)
        recurse(cold, m, iz * tree.c[cold] / rj, 0.0, f)

    recurse(0, [], 1.0, 1.0, -1)


def explain(values: Dict[str, float]) -> dict:
    feats, trees = model()
    x = [values.get(f) for f in feats]
    if any(v is None for v in x):
        missing = [f for f, v in zip(feats, x) if v is None]
        raise HTTPException(422, f"Missing features: {missing}")
    phi = [0.0] * len(feats)
    for t in trees:
        tree_shap(t, x, phi)
    base = sum(t.expected() for t in trees)
    score = sum(t.predict(x) for t in trees)
    return {"score": score, "base": base,
            "contributions": sorted(({"feature": f, "value": v, "shap": p} for f, v, p in zip(feats, x, phi)),
                                    key=lambda d: -abs(d["shap"]))}


def placement(score: float) -> dict:
    """Where a score would sit among today's universe, and the signal and odds that implies."""
    rows = load("signals")["rows"]
    meta = load("meta")
    n = len(rows)
    below = sum(1 for r in rows if r["score"] < score)
    pct = (below + 0.5) / n if n else 0.5
    if pct > 1 - meta["buyTopPct"]:
        sig = "BUY"
    elif pct <= meta["avoidBottomPct"]:
        sig = "AVOID"
    else:
        sig = "HOLD"
    decile = min(10, max(1, math.ceil(pct * 10)))
    cal = {c["decile"]: c for c in load("metrics")["calibration"]}.get(decile, {})
    return {"pct": pct, "rank": n - below, "of": n, "signal": sig, "decile": decile,
            "odds": cal.get("hitRate"), "meanExcess": cal.get("meanExcess")}


# ---------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    meta = load("meta")
    return {"status": "ok", "asof": meta["asof"], "generatedAt": meta["generatedAt"],
            "model": meta["model"].get("version")}


@app.get("/api/meta")
def get_meta():
    return load("meta")


@app.get("/api/signals")
def get_signals(signal: Optional[str] = None, q: Optional[str] = None, limit: int = 400):
    data = load("signals")
    rows = data["rows"]
    if signal:
        rows = [r for r in rows if r["signal"] == signal.upper()]
    if q:
        rows = [r for r in rows if q.upper() in r["symbol"]]
    return {"asof": data["asof"], "n": data["n"], "rows": rows[:max(1, min(limit, 1000))]}


@app.get("/api/stock/{symbol}")
def get_stock(symbol: str):
    symbol = symbol.upper()
    feats = load("features")
    if symbol not in feats["values"]:
        raise HTTPException(404, f"{symbol} is not in today's universe")
    row = next(r for r in load("signals")["rows"] if r["symbol"] == symbol)
    t0 = time.perf_counter()
    ex = explain(feats["values"][symbol])
    return {"asof": feats["asof"], "signal": row, "history": load("history")["data"].get(symbol, []),
            "historyCols": load("history")["cols"], "features": feats["values"][symbol],
            "explanation": ex, "families": feats["families"], "ranges": feats["ranges"],
            "computeMs": round((time.perf_counter() - t0) * 1000, 1)}


class ScoreRequest(BaseModel):
    symbol: str = Field(..., description="Ticker whose latest features are the starting point")
    overrides: Dict[str, float] = Field(default_factory=dict, description="Feature values to change")


@app.post("/api/score")
def post_score(req: ScoreRequest):
    feats = load("features")
    base_vals = feats["values"].get(req.symbol.upper())
    if base_vals is None:
        raise HTTPException(404, f"{req.symbol} is not in today's universe")
    unknown = set(req.overrides) - set(base_vals)
    if unknown:
        raise HTTPException(422, f"Unknown features: {sorted(unknown)}")
    t0 = time.perf_counter()
    ex = explain({**base_vals, **req.overrides})
    return {**ex, "placement": placement(ex["score"]), "overrides": req.overrides,
            "computeMs": round((time.perf_counter() - t0) * 1000, 1)}


@app.get("/api/metrics")
def get_metrics():
    return load("metrics")


@app.get("/api/regime")
def get_regime():
    return load("regime")
