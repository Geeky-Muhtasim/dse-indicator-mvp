"""Self-contained HTML research report: signals today, and evidence for whether to trust them."""
from __future__ import annotations

import base64
import html
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import math
import numpy as np
import pandas as pd

# Palette validated for CVD separation and contrast on the panel colour.
INK, MUTED, RULE, PANEL = "#171512", "#5E574B", "#D6CCB8", "#FBF8F2"
GBM, CARD, BENCH = "#C8401C", "#1F6AA5", "#A07CC8"
POS, NEG = "#1F6AA5", "#C8401C"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": "#ECE5D6", "grid.linewidth": 0.8, "axes.axisbelow": True,
    "figure.facecolor": PANEL, "axes.facecolor": PANEL, "savefig.facecolor": PANEL,
})


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _pct(x, d=1, sign=False):
    if x is None or not np.isfinite(x):
        return "n/a"
    return f"{x:+.{d}%}" if sign else f"{x:.{d}%}"


def _dates(ax):
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.SU, interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.tick_params(axis="x", rotation=0)


def chart_ic(ic: pd.Series) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    x = pd.to_datetime(ic.index)
    ax.bar(x, ic.values, width=0.8, color=[POS if v >= 0 else NEG for v in ic.values])
    ax.axhline(0, color=INK, lw=0.8)
    ax.axhline(ic.mean(), color=INK, lw=1, ls=(0, (4, 3)))
    ax.text(x[-1], ic.mean(), f"  mean {ic.mean():.3f}", va="center", ha="left", color=INK, fontsize=9)
    ax.set_ylabel("Rank IC")
    _dates(ax)
    return _png(fig)


def chart_quintiles(q_gbm: dict, q_card: dict) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    qs = np.arange(1, 6)
    w = 0.38
    g = [q_gbm[k] * 100 for k in qs]
    c = [q_card[k] * 100 for k in qs]
    ax.bar(qs - w / 2 - 0.01, g, w, color=GBM, label="LightGBM")
    ax.bar(qs + w / 2 + 0.01, c, w, color=CARD, label="Scorecard")
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_xticks(qs, ["Q1\nlowest score", "Q2", "Q3", "Q4", "Q5\nhighest score"])
    ax.set_ylabel("Mean 5-day excess return (%)")
    ax.legend(frameon=False, loc="upper left")
    return _png(fig)


def chart_calibration(calib: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ax.bar(calib.index, calib["hit_rate"] * 100, width=0.75, color=CARD)
    ax.axhline(50, color=INK, lw=1, ls=(0, (4, 3)))
    ax.text(0.45, 51, "coin flip", va="bottom", color=INK, fontsize=9)
    for d, v in calib["hit_rate"].items():
        if d in (1, 10):
            ax.text(d, v * 100 + 1, f"{v:.0%}", ha="center", color=INK, fontsize=9)
    ax.set_ylim(30, 65)
    ax.set_xticks(range(1, 11))
    ax.set_xlabel("Score decile (out of sample)")
    ax.set_ylabel("% beating the market")
    return _png(fig)


def chart_equity(bt_g: pd.DataFrame, bt_c: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    def line(bt, col, color, label, ls="-"):
        x = list(pd.to_datetime(bt.index)) + [pd.to_datetime(bt.index[-1]) + pd.Timedelta(days=7)]
        y = [1.0] + list(bt[col].values)
        ax.plot(x, [(v - 1) * 100 for v in y], color=color, lw=2, ls=ls, marker="o", ms=4,
                label=f"{label}  {(y[-1] - 1):+.1%}")
    line(bt_g, "cum_net", GBM, "LightGBM top decile, net")
    line(bt_c, "cum_net", CARD, "Scorecard top decile, net")
    line(bt_g, "cum_bench", BENCH, "Equal-weight market", ls=(0, (5, 3)))
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_ylabel("Cumulative return (%)")
    _dates(ax)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=1, fontsize=9)
    return _png(fig)


def chart_families(imp: pd.Series) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    imp = imp.sort_values()
    ax.barh(imp.index, imp.values, color=CARD, height=0.6)
    for i, v in enumerate(imp.values):
        ax.text(v, i, f" {v / imp.sum():.0%}", va="center", color=INK, fontsize=9)
    ax.set_xlabel("Mean |SHAP| on score (share of total shown)")
    ax.grid(axis="y", visible=False)
    return _png(fig)


def chart_breadth(br: pd.Series, threshold: float) -> str:
    fig, ax = plt.subplots(figsize=(14.5, 3.0))
    x = pd.to_datetime(br.index)
    ax.plot(x, br.values * 100, color=CARD, lw=2)
    ax.axhline(threshold * 100, color=NEG, lw=1, ls=(0, (4, 3)))
    ax.text(x[0], threshold * 100 + 2, "risk-off line", color=INK, fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% above 20-day MA")
    _dates(ax)
    return _png(fig)


def _driver_rows(drv: list[dict], sign: str, scale: float) -> str:
    out = []
    for d in drv:
        w = min(100, abs(d["shap"]) / scale * 100) if scale else 0
        cls = "pos" if sign == "+" else "neg"
        out.append(f'<div class="drv"><span class="sg {cls}">{sign}</span>'
                   f'<span class="dt">{html.escape(d["text"])}</span>'
                   f'<span class="bar"><i class="{cls}" style="width:{w:.0f}%"></i></span>'
                   f'<span class="sv">{d["shap"]:+.3f}</span></div>')
    return "".join(out)


def _card(r: pd.Series, scale: float) -> str:
    risk = '<span class="flag">limit move today: fill risk</span>' if r["fill_risk"] else ""
    return f"""
<article class="card">
  <header><div><h3>{html.escape(r['Symbol'])}</h3><span class="px">Tk {r['Close']:,.1f}</span></div>
  <span class="stamp {r['signal'].lower()}">{r['signal']}</span></header>
  <p class="meta">Score in the top {max(1, math.ceil((1 - r['pct']) * 100))}% · decile {r['decile']} historically beat the market
  {_pct(r['hist_hit_rate'], 0)} of the time, mean excess {_pct(r['hist_mean_excess'], 2, True)}</p>
  {_driver_rows(r['drivers_for'], '+', scale)}
  {_driver_rows(r['drivers_against'][:1], '−', scale)}
  <p class="why">{html.escape(r['rationale'])}</p>{risk}
</article>"""


CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap');
:root{--paper:#F3EEE4;--panel:#FBF8F2;--ink:#171512;--muted:#5E574B;--rule:#D6CCB8;--acc:#C8401C;--blue:#1F6AA5}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);background-image:linear-gradient(#E6DFD0 1px,transparent 1px),linear-gradient(90deg,#E6DFD0 1px,transparent 1px);background-size:24px 24px;color:var(--ink);font:16px/1.55 'IBM Plex Sans',Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:48px 24px 80px}
.mono{font-family:'IBM Plex Mono',monospace}
.eyebrow{font:600 13px/1 'IBM Plex Mono',monospace;letter-spacing:.14em;color:var(--acc)}
h1{font:400 clamp(40px,6vw,72px)/1.02 'Instrument Serif',Georgia,serif;margin:12px 0 12px;letter-spacing:-.01em}
h1 i{font-style:italic}
h2{font:400 36px/1.1 'Instrument Serif',Georgia,serif;margin:0}
h3{font:400 30px/1 'Instrument Serif',Georgia,serif;margin:0}
.lede{color:var(--muted);max-width:760px;font-size:18px;margin:0}
section{margin-top:56px}
.rule{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid var(--ink);padding-bottom:10px;margin-bottom:20px;gap:16px;flex-wrap:wrap}
.rule .mono{font-size:13px;letter-spacing:.12em;color:var(--muted)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(200px,100%),1fr));gap:0;border:1.5px solid var(--ink);background:var(--panel);margin-top:32px}
.tile{padding:18px 20px;border-right:1px solid var(--rule)}
.tile:last-child{border-right:0}
.tile .k{font:600 12px/1.3 'IBM Plex Mono',monospace;letter-spacing:.12em;color:var(--muted)}
.tile .v{font:400 44px/1.1 'Instrument Serif',Georgia,serif;margin-top:6px}
.tile .s{font-size:14px;color:var(--muted)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(520px,100%),1fr));gap:20px}
.panel{background:var(--panel);border:1.5px solid var(--ink);padding:20px}
.panel .cap{font:600 12px/1.3 'IBM Plex Mono',monospace;letter-spacing:.12em;margin-bottom:10px}
.panel img{width:100%;height:auto;display:block}
.panel p{margin:10px 0 0;color:var(--muted);font-size:15px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(360px,100%),1fr));gap:20px}
.card{background:var(--panel);border:1.5px solid var(--ink);padding:20px}
.card header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
.card .px{font:500 14px 'IBM Plex Mono',monospace;color:var(--muted);display:block;margin-top:6px}
.stamp{font:600 18px/1 'IBM Plex Mono',monospace;letter-spacing:.18em;padding:6px 12px;border:2.5px solid;transform:rotate(-4deg)}
.stamp.buy{color:var(--blue)}.stamp.avoid{color:var(--acc)}.stamp.hold{color:var(--muted)}
.meta{font-size:14px;color:var(--muted);margin:4px 0 12px}
.drv{display:grid;grid-template-columns:16px minmax(0,1fr) 90px 56px;gap:10px;align-items:center;font-size:14px;padding:6px 0;border-top:1px solid var(--rule)}
.sg{font:600 15px 'IBM Plex Mono',monospace}.sg.pos{color:var(--blue)}.sg.neg{color:var(--acc)}
.bar{height:9px;border-bottom:1px solid var(--ink);display:flex;align-items:flex-end}
.bar i{display:block;height:8px}.bar i.pos{background:var(--blue)}.bar i.neg{background:repeating-linear-gradient(45deg,var(--acc) 0 2px,transparent 2px 5px);border:1px solid var(--acc)}
.sv{font:500 13px 'IBM Plex Mono',monospace;text-align:right}
.why{font:italic 19px/1.35 'Instrument Serif',Georgia,serif;margin:12px 0 0}
.flag{display:inline-block;margin-top:10px;font:600 12px 'IBM Plex Mono',monospace;color:var(--acc);letter-spacing:.08em}
.tbl{overflow-x:auto;background:var(--panel);border:1.5px solid var(--ink)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:9px 12px;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top}
th{font:600 12px 'IBM Plex Mono',monospace;letter-spacing:.1em;color:var(--muted);border-bottom:1.5px solid var(--ink)}
td.n{font-family:'IBM Plex Mono',monospace;text-align:right;white-space:nowrap}
.verdict{background:var(--ink);color:var(--panel);padding:22px 26px;margin-top:20px}
.verdict .k{font:600 12px 'IBM Plex Mono',monospace;letter-spacing:.14em;color:#FF7A52}
.verdict p{margin:8px 0 0;font:400 22px/1.35 'Instrument Serif',Georgia,serif}
ol.notes{margin:0;padding-left:22px}ol.notes li{margin:6px 0}
footer{margin-top:56px;font:500 13px 'IBM Plex Mono',monospace;color:var(--muted)}
"""


def build(res: dict) -> str:
    m_g, m_c = res["metrics"]["gbm"], res["metrics"]["card"]
    sig, reg, cfg = res["signals"], res["regime"], res["cfg"]
    buys = sig[sig.signal == "BUY"]
    avoids = sig[sig.signal == "AVOID"].sort_values("score")
    scale = max((abs(d["shap"]) for drv in buys["drivers_for"] for d in drv), default=1)

    edge_gross = m_g["bt_gross_total"] - m_g["bt_bench_total"]
    edge_net = m_g["bt_net_total"] - m_g["bt_bench_total"]
    beats_card = m_g["ic_mean"] > m_c["ic_mean"]
    verdict = (
        f"The ranking carries information out of sample (mean rank IC {m_g['ic_mean']:.3f}, positive on "
        f"{m_g['ic_positive_share']:.0%} of days, top quintile {_pct(m_g['quintile_excess'][5], 2, True)} vs bottom "
        f"{_pct(m_g['quintile_excess'][1], 2, True)} per {cfg.horizon} days). "
        + (f"Before costs the top decile {'beat' if edge_gross > 0 else 'trailed'} the market by {_pct(edge_gross, 1, True)}; "
           f"after {cfg.round_trip_cost:.2%} round-trip costs at {m_g['bt_avg_turnover']:.0%} turnover it is {_pct(edge_net, 1, True)}. ")
        + f"With only {m_g['bt_periods']} independent periods and a t-stat of {m_g['ic_tstat_nonoverlap']:.2f}, "
        "none of this is statistically conclusive yet. Treat it as a working pipeline, not a trading edge."
    )

    reg_txt = ("Risk-off: breadth is weak and the market is falling, so the Buy bucket is tightened to the top "
               f"{cfg.buy_top_pct_risk_off:.0%}." if reg["risk_off"] else
               f"Normal: Buy bucket is the top {cfg.buy_top_pct:.0%} of scores.")

    q = res["quality"]
    metric_rows = [
        ("Mean daily rank IC", f"{m_g['ic_mean']:.3f}", f"{m_c['ic_mean']:.3f}"),
        ("IC positive days", _pct(m_g["ic_positive_share"], 0), _pct(m_c["ic_positive_share"], 0)),
        ("IC t-stat (non-overlapping)", f"{m_g['ic_tstat_nonoverlap']:.2f}", f"{m_c['ic_tstat_nonoverlap']:.2f}"),
        ("Q5 minus Q1, per period", _pct(m_g["q5_minus_q1"], 2, True), _pct(m_c["q5_minus_q1"], 2, True)),
        ("Top decile, gross", _pct(m_g["bt_gross_total"], 1, True), _pct(m_c["bt_gross_total"], 1, True)),
        ("Top decile, net of costs", _pct(m_g["bt_net_total"], 1, True), _pct(m_c["bt_net_total"], 1, True)),
        ("Equal-weight market", _pct(m_g["bt_bench_total"], 1, True), _pct(m_c["bt_bench_total"], 1, True)),
        ("Periods beating market (net)", _pct(m_g["bt_net_hit_vs_bench"], 0), _pct(m_c["bt_net_hit_vs_bench"], 0)),
        ("Average turnover", _pct(m_g["bt_avg_turnover"], 0), _pct(m_c["bt_avg_turnover"], 0)),
        ("Max drawdown, net", _pct(m_g["bt_max_drawdown_net"], 1), _pct(m_c["bt_max_drawdown_net"], 1)),
    ]
    mt = "".join(f"<tr><td>{a}</td><td class='n'>{b}</td><td class='n'>{c}</td></tr>" for a, b, c in metric_rows)

    fold_rows = "".join(
        f"<tr><td class='n'>{f['fold']}</td><td>{f['train_start']} to {f['train_end']}</td>"
        f"<td>{f['test_start']} to {f['test_end']}</td><td class='n'>{f['train_rows']:,}</td></tr>"
        for f in res["folds"])

    avoid_rows = "".join(
        f"<tr><td class='mono'>{html.escape(r.Symbol)}</td><td class='n'>{r.Close:,.1f}</td>"
        f"<td class='n'>{_pct(r.hist_hit_rate, 0)}</td><td>{html.escape(r.rationale)}</td></tr>"
        for r in avoids.head(12).itertuples())

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DSE Signal Report {res['asof']}</title><style>{CSS}</style></head><body><div class="wrap">

<div class="eyebrow">DSE EXPLAINABLE SIGNAL · v0.1 · AS OF {res['asof']}</div>
<h1>Which DSE stocks to <i>favour</i>, and why.</h1>
<p class="lede">A cross-sectional ranking of {res['n_universe']} liquid Dhaka Stock Exchange equities on end-of-day
data from {q['start']} to {q['end']}. Each call is traced to its drivers with SHAP, and the model is judged
only on purged walk-forward, out-of-sample results with trading costs included.</p>

<div class="tiles">
  <div class="tile"><div class="k">RANK IC, OOS</div><div class="v">{m_g['ic_mean']:.3f}</div><div class="s">scorecard {m_c['ic_mean']:.3f}</div></div>
  <div class="tile"><div class="k">Q5 − Q1 SPREAD</div><div class="v">{_pct(m_g['q5_minus_q1'], 2, True)}</div><div class="s">per {cfg.horizon}-day period</div></div>
  <div class="tile"><div class="k">TOP DECILE vs MARKET</div><div class="v">{_pct(edge_net, 1, True)}</div><div class="s">net of costs · gross {_pct(edge_gross, 1, True)}</div></div>
  <div class="tile"><div class="k">TODAY</div><div class="v">{len(buys)} / {len(avoids)}</div><div class="s">Buy / Avoid calls</div></div>
  <div class="tile"><div class="k">REGIME</div><div class="v">{'Risk-off' if reg['risk_off'] else 'Normal'}</div><div class="s">breadth {reg['breadth_20']:.0%} · mkt {_pct(reg['mkt_ret_10'], 1, True)} 10d</div></div>
</div>

<div class="verdict"><div class="k">VERDICT</div><p>{html.escape(verdict)}</p></div>

<section><div class="rule"><h2>Buy calls for {res['asof']}</h2><span class="mono">I. SIGNALS · {html.escape(reg_txt)}</span></div>
<div class="cards">{''.join(_card(r, scale) for _, r in buys.iterrows())}</div></section>

<section><div class="rule"><h2>Avoid list</h2><span class="mono">BOTTOM {cfg.avoid_bottom_pct:.0%} · FIRST 12 SHOWN · FULL LIST IN signals_latest.csv</span></div>
<div class="tbl"><table><thead><tr><th>SYMBOL</th><th>CLOSE</th><th>DECILE HIT RATE</th><th>WHY</th></tr></thead><tbody>{avoid_rows}</tbody></table></div></section>

<section><div class="rule"><h2>Does the ranking work?</h2><span class="mono">II. OUT-OF-SAMPLE EVIDENCE</span></div>
<div class="grid2">
 <div class="panel"><div class="cap">FIG. 1 DAILY RANK IC, LIGHTGBM</div><img src="{res['charts']['ic']}" alt="Daily rank information coefficient">
 <p>Spearman correlation between each day's scores and the next {cfg.horizon}-day excess returns. Above zero means the ranking pointed the right way.</p></div>
 <div class="panel"><div class="cap">FIG. 2 RETURNS BY SCORE QUINTILE</div><img src="{res['charts']['quint']}" alt="Excess return by score quintile">
 <p>A useful score climbs from Q1 to Q5. Both models are scored on the same out-of-sample dates.</p></div>
 <div class="panel"><div class="cap">FIG. 3 HIT RATE BY DECILE (CONFIDENCE SOURCE)</div><img src="{res['charts']['calib']}" alt="Hit rate by score decile">
 <p>Each signal's confidence is read from this table rather than from the raw model output, so it is calibrated by construction.</p></div>
 <div class="panel"><div class="cap">FIG. 4 WHAT THE MODEL LEANS ON</div><img src="{res['charts']['fam']}" alt="SHAP importance by feature family">
 <p>Mean absolute SHAP contribution, grouped into the families used in every explanation.</p></div>
</div></section>

<section><div class="rule"><h2>Can you trade it?</h2><span class="mono">III. COST-AWARE BACKTEST</span></div>
<div class="grid2">
 <div class="panel"><div class="cap">FIG. 5 TOP-DECILE PORTFOLIO vs MARKET</div><img src="{res['charts']['eq']}" alt="Cumulative returns">
 <p>Rebalanced every {cfg.horizon} days, entry at next open, exit at close. Names that open locked at a limit are treated as unfilled. Costs: {cfg.round_trip_cost:.2%} per round trip, charged on turnover.</p></div>
 <div class="tbl"><table><thead><tr><th>METRIC</th><th>LIGHTGBM</th><th>SCORECARD</th></tr></thead><tbody>{mt}</tbody></table></div>
</div>
<p class="lede" style="margin-top:16px">{'The learned model ranks better than the transparent scorecard, which is the minimum bar for using it.' if beats_card else 'The learned model does not yet beat the transparent scorecard, so the scorecard is the honest choice until more data says otherwise.'}</p>
</section>

<section><div class="rule"><h2>Market regime</h2><span class="mono">IV. BREADTH GATE</span></div>
<div class="panel"><div class="cap">FIG. 6 SHARE OF UNIVERSE ABOVE ITS 20-DAY AVERAGE</div><img src="{res['charts']['breadth']}" alt="Market breadth"></div></section>

<section><div class="rule"><h2>Method and limits</h2><span class="mono">V. NOTES</span></div>
<div class="grid2">
<div class="panel"><div class="cap">PIPELINE</div><ol class="notes">
<li>Universe: {q['instrument_mix'].get('equity', 0)} equities after removing {q['instrument_mix'].get('fund', 0)} funds and {q['instrument_mix'].get('bond', 0)} bonds; bottom {cfg.liquidity_drop_quantile:.0%} by 20-day median turnover dropped, recomputed daily.</li>
<li>Features: 19 point-in-time signals in six families (momentum, trend, volatility, volume, relative strength, regime).</li>
<li>Target: cross-sectional rank of {cfg.horizon}-day excess return over the equal-weight market, entry at next open.</li>
<li>Models: an unfitted five-factor scorecard as baseline; LightGBM regression on the rank target.</li>
<li>Validation: expanding walk-forward; training rows whose label window reaches the test block are purged.</li>
<li>Explanations: TreeSHAP per stock; rationale text is built only from those attributions.</li>
</ol></div>
<div class="panel"><div class="cap">LIMITATIONS</div><ol class="notes">
<li>{q['trading_days']} trading days in one falling market. Every metric here has wide error bars.</li>
<li>Cost assumptions ({cfg.commission_bps_per_side:.0f} bps commission + {cfg.slippage_bps_per_side:.0f} bps slippage per side) are estimates; set yours in config.py.</li>
<li>No dividends, rights or sector data yet. Adjusted prices are taken as given from StockNow.</li>
<li>{q['limit_like_moves']} limit-like daily moves and {q['flat_bars']} flat bars in the data; fills near circuit breakers are uncertain.</li>
<li>Not investment advice. This is a research tool.</li>
</ol></div>
</div>
<div class="tbl" style="margin-top:20px"><table><thead><tr><th>FOLD</th><th>TRAIN</th><th>TEST</th><th>TRAIN ROWS</th></tr></thead><tbody>{fold_rows}</tbody></table></div>
</section>

<footer>Generated by dse_signal v0.1 · data {q['start']} to {q['end']} · {q['rows']:,} rows · {q['symbols']} symbols</footer>
</div></body></html>"""
