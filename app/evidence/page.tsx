"use client";
import { LineChart, ZeroBars } from "@/components/charts";
import { L, V, useLang } from "@/components/lang";
import { ErrorBox, Loading, PageHead } from "@/components/ui";
import { useApi } from "@/lib/api";
import { FAMILY, dateLabel, pct, toBn } from "@/lib/i18n";

type Sum = {
  ic_mean: number; ic_positive_share: number; ic_tstat_nonoverlap: number; quintile_excess: Record<string, number>;
  q5_minus_q1: number; bt_periods: number; bt_gross_total: number; bt_net_total: number; bt_bench_total: number;
  bt_net_hit_vs_bench: number; bt_avg_turnover: number; bt_max_drawdown_net: number;
  bt_years?: number; bt_ann_net?: number; bt_ann_bench?: number; bt_info_ratio_net?: number;
};
type BT = { date: string; cum_net: number; cum_bench: number; cum_gross: number }[];
type Metrics = {
  asofValidation: string; summary: { gbm: Sum; card: Sum }; icSeries: { date: string; ic: number }[]; icFreq?: "daily" | "monthly";
  calibration: { decile: number; hitRate: number; meanExcess: number; n: number }[];
  backtest: { gbm: BT; card: BT }; folds: { fold: number; train_start: string; train_end: string; test_start: string; test_end: string; train_rows: number }[];
  familyImportance: Record<string, number>; config: { horizon: number; roundTripCost: number; commissionBps: number; slippageBps: number };
  quality: { trading_days: number; start: string; end: string };
};

const days = (a: string, b: string) => (Date.parse(b) - Date.parse(a)) / 864e5;

export default function EvidencePage() {
  const { lang } = useLang();
  const { data: m, error } = useApi<Metrics>("/metrics");
  const P = (x: number, d = 1, s = false) => <V p={pct(x, d, s)} />;

  if (error) return <><PageHead title="Model evidence" /><div className="content"><ErrorBox msg={error} /></div></>;
  const g = m?.summary.gbm, c = m?.summary.card;
  const edgeGross = g ? g.bt_gross_total - g.bt_bench_total : 0;
  const edgeNet = g ? g.bt_net_total - g.bt_bench_total : 0;
  const t0 = m?.folds[0]?.train_start, t1 = m?.folds[m.folds.length - 1]?.test_end;
  const span = t0 && t1 ? days(t0, t1) : 1;

  return (
    <>
      <PageHead crumb={<L en="Out of sample, costs included" bn="আউট-অব-স্যাম্পল, খরচসহ" />}
        title={<L en="Does the model actually work?" bn="মডেল কি সত্যিই কাজ করে?" />}
        lede="Every number here comes from dates the model never trained on." />
      <div className="content">
        {!m || !g || !c ? <Loading h={420} /> : (
          <>
            <section className="verdict gd" aria-label="Verdict">
              <div style={{ flex: "1 1 480px", lineHeight: 1.45 }}>
                <div style={{ fontSize: 13, color: "#9DB5A8", fontWeight: 500 }}><L en="Verdict" bn="রায়" /></div>
                {lang === "bi" && <div style={{ fontSize: 20, fontWeight: 500, marginTop: 4 }}>
                  {g.ic_mean > 0 ? "র‍্যাঙ্কিং তথ্য বহন করে" : "র‍্যাঙ্কিং এখনও কাজ করছে না"}{edgeNet < 0 ? ", কিন্তু লেনদেন খরচ সুবিধাটুকু খেয়ে ফেলে" : ""}। প্রমাণ এখনও {Math.abs(g.ic_tstat_nonoverlap) < 2 ? "দুর্বল" : "জোরালো"}।
                </div>}
                <div className="en" style={{ fontSize: lang === "bi" ? 14 : 19, color: lang === "bi" ? "#B9CEC2" : "#F8FAF7", marginTop: 4 }}>
                  {g.ic_mean > 0 ? "The ranking carries information" : "The ranking is not yet informative"}
                  {edgeNet < 0 ? `, but at a ${m.config.horizon}-session horizon trading costs eat the edge` : ", and the edge survives costs"}.
                  {" "}Only {g.bt_periods} independent periods (t = {g.ic_tstat_nonoverlap.toFixed(2)}): {Math.abs(g.ic_tstat_nonoverlap) < 2 ? "a working pipeline, not yet a proven edge." : "a promising result worth more data."}
                </div>
              </div>
              <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
                <span style={{ lineHeight: 1.2 }}><span className="num" style={{ display: "block", fontSize: 30, fontWeight: 600 }}>{P(edgeGross, 1, true)}</span><span className="en" style={{ fontSize: 12, color: "#9DB5A8" }}>vs market, gross</span></span>
                <span style={{ lineHeight: 1.2 }}><span className="num" style={{ display: "block", fontSize: 30, fontWeight: 600, color: edgeNet < 0 ? "#F7B3C9" : "#A9E3C3" }}>{P(edgeNet, 1, true)}</span><span className="en" style={{ fontSize: 12, color: "#9DB5A8" }}>vs market, after costs</span></span>
              </div>
            </section>

            <div className="row">
              <section className="card" aria-label="Daily rank IC">
                <div className="card-head"><h2>{m.icFreq === "monthly" ? <L en="Rank IC by month" bn="মাসভিত্তিক র‍্যাঙ্ক আইসি" /> : <L en="Daily rank IC" bn="দৈনিক র‍্যাঙ্ক আইসি" />}</h2><span className="en muted" style={{ fontSize: 12 }}>Mean {g.ic_mean.toFixed(3)} · positive {Math.round(g.ic_positive_share * 100)}% of days{m.icFreq === "monthly" ? " · bars are monthly means" : ""}</span></div>
                <div style={{ marginTop: 14 }}>
                  <ZeroBars values={m.icSeries.map((d) => d.ic)} labels={m.icSeries.map((d) => d.date)} fmt={(v) => v.toFixed(3)} meanLine={g.ic_mean} />
                  <div className="axis"><span><V p={dateLabel(m.icSeries[0].date)} /></span><span><V p={dateLabel(m.icSeries[m.icSeries.length - 1].date)} /></span></div>
                </div>
                <p className="note"><L en={`Correlation between each day's scores and the next ${m.config.horizon} sessions' excess returns. Above zero: the ranking pointed the right way. Dashed line: mean.`} bn="প্রতিদিনের স্কোর বনাম পরের সেশনগুলোর অতিরিক্ত রিটার্নের সম্পর্ক। শূন্যের ওপরে মানে র‍্যাঙ্কিং ঠিক দিকে ছিল।" /></p>
              </section>

              <section className="card" aria-label="Returns by quintile">
                <div className="card-head"><h2><L en="Excess return by score quintile" bn="স্কোর পঞ্চমাংশে রিটার্ন" /></h2>
                  <span className="legend"><span><span className="sw" style={{ background: "#262B6B" }} />LightGBM</span><span><span className="sw" style={{ background: "#C3C7E8", border: "1px solid #8F95C9" }} />Scorecard</span></span></div>
                <div style={{ marginTop: 14 }}>
                  {(() => {
                    const qs = [1, 2, 3, 4, 5];
                    const mx = Math.max(...qs.flatMap((q) => [Math.abs(g.quintile_excess[q]), Math.abs(c.quintile_excess[q])]));
                    const bar = (v: number, up: boolean, fill: string, border?: string) => (
                      <span style={{ flex: 1, height: (v > 0) === up && v !== 0 ? `${(Math.abs(v) / mx) * 100}%` : 0, background: fill, border: border && v !== 0 && (v > 0) === up ? `1px solid ${border}` : undefined }} title={`${(v * 100).toFixed(2)}%`} />
                    );
                    return (
                      <div style={{ height: 220, display: "flex", flexDirection: "column" }}>
                        <div style={{ height: 110, display: "flex", gap: 18, alignItems: "flex-end", borderBottom: "1px solid #0F2A22", padding: "0 10px" }}>
                          {qs.map((q) => <span key={q} style={{ flex: 1, display: "flex", gap: 3, alignItems: "flex-end", height: "100%" }}>{bar(g.quintile_excess[q], true, "#262B6B")}{bar(c.quintile_excess[q], true, "#C3C7E8", "#8F95C9")}</span>)}
                        </div>
                        <div style={{ height: 110, display: "flex", gap: 18, alignItems: "flex-start", padding: "0 10px" }}>
                          {qs.map((q) => <span key={q} style={{ flex: 1, display: "flex", gap: 3, alignItems: "flex-start", height: "100%" }}>{bar(g.quintile_excess[q], false, "#262B6B")}{bar(c.quintile_excess[q], false, "#C3C7E8", "#8F95C9")}</span>)}
                        </div>
                      </div>
                    );
                  })()}
                  <div className="axis" style={{ padding: "6px 10px 0" }}>{["Q1 lowest", "Q2", "Q3", "Q4", "Q5 highest"].map((t) => <span key={t} className="en" style={{ flex: 1, textAlign: "center" }}>{t}</span>)}</div>
                </div>
                <p className="note">Per {m.config.horizon}-session period. Q5 − Q1: LightGBM {pct(g.q5_minus_q1, 2, true).en}, scorecard {pct(c.q5_minus_q1, 2, true).en}. A useful score climbs from Q1 to Q5.</p>
              </section>
            </div>

            <div className="row">
              <section className="card" aria-label="Hit rate by decile">
                <div className="card-head"><h2><L en="Where the odds come from" bn="আস্থা কোথা থেকে আসে" /></h2><span className="en muted" style={{ fontSize: 12 }}>% beating the market, by score decile</span></div>
                <div style={{ display: "grid", gridTemplateColumns: "40px minmax(0,1fr)", marginTop: 14 }}>
                  <div className="num muted" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", fontSize: 12, height: 180 }}><span><V p={pct(0.6, 0)} /></span><span><V p={pct(0.45, 0)} /></span><span><V p={pct(0.3, 0)} /></span></div>
                  <div className="bars" style={{ height: 180, gap: 8, borderBottom: "1px solid #0F2A22", position: "relative" }}>
                    <span style={{ position: "absolute", left: 0, right: 0, bottom: "66.7%", borderTop: "1px dashed #0F2A22", flex: "none" }} />
                    {m.calibration.map((d) => (
                      <span key={d.decile} title={`Decile ${d.decile}: ${(d.hitRate * 100).toFixed(1)}% (n=${d.n})`}
                        style={{ height: `${Math.max(0, Math.min(100, ((d.hitRate - 0.3) / 0.3) * 100))}%`, background: d.decile >= 9 ? "#262B6B" : "#C3C7E8", borderRadius: "3px 3px 0 0" }} />
                    ))}
                  </div>
                  <span />
                  <div className="axis">{m.calibration.map((d) => <span key={d.decile} style={{ flex: 1, textAlign: "center" }}><V p={{ en: String(d.decile), bn: toBn(String(d.decile)) }} /></span>)}</div>
                </div>
                <p className="note"><L en="Each signal's odds are read from this table, not from the raw model output, so they are calibrated by construction. Dashed line: 50%, a coin flip." bn="প্রতিটি সংকেতের আস্থা এই সারণি থেকে পড়া হয়, মডেলের কাঁচা আউটপুট থেকে নয়। ড্যাশ রেখা: ৫০%।" /></p>
              </section>

              <section className="card" aria-label="Backtest">
                <div className="card-head"><h2><L en="If you had traded it" bn="লেনদেন করলে কী হতো" /></h2>
                  <span className="legend"><span><span className="sw" style={{ height: 2, background: "#262B6B" }} />LightGBM net</span><span><span className="sw" style={{ height: 2, background: "#1F7A55" }} />Scorecard net</span><span><span className="sw" style={{ height: 0, borderTop: "2px dashed #4A6458" }} />Market</span></span></div>
                <div style={{ marginTop: 8 }}>
                  <LineChart ariaLabel="Cumulative return of top-decile portfolios versus the market" height={200}
                    labels={["Start", ...m.backtest.gbm.map((r) => dateLabel(r.date).en)]}
                    yFmt={(v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%`}
                    series={[
                      { name: "Market", color: "#4A6458", dash: "5 4", values: [0, ...m.backtest.gbm.map((r) => (r.cum_bench - 1) * 100)] },
                      { name: "Scorecard net", color: "#1F7A55", values: [0, ...m.backtest.card.map((r) => (r.cum_net - 1) * 100)] },
                      { name: "LightGBM net", color: "#262B6B", values: [0, ...m.backtest.gbm.map((r) => (r.cum_net - 1) * 100)] },
                    ]} />
                </div>
                <div className="tbl" style={{ marginTop: 8 }}>
                  <table>
                    <thead><tr><th><L en="Metric" bn="মাপকাঠি" /></th><th className="r en">LightGBM</th><th className="r en">Scorecard</th></tr></thead>
                    <tbody>
                      {[
                        [{ en: "Gross return", bn: "খরচের আগে" }, g.bt_gross_total, c.bt_gross_total],
                        [{ en: "Net of costs", bn: "খরচের পরে" }, g.bt_net_total, c.bt_net_total],
                        [{ en: "Equal-weight market", bn: "সমান-ওজনের বাজার" }, g.bt_bench_total, c.bt_bench_total],
                        [{ en: "Average turnover", bn: "গড় টার্নওভার" }, g.bt_avg_turnover, c.bt_avg_turnover],
                        [{ en: "Max drawdown, net", bn: "সর্বোচ্চ পতন" }, g.bt_max_drawdown_net, c.bt_max_drawdown_net],
                        ...((g.bt_years ?? 0) >= 1 ? [
                          [{ en: "Annualised, net", bn: "বার্ষিক, খরচের পরে" }, g.bt_ann_net ?? 0, c.bt_ann_net ?? 0],
                          [{ en: "Annualised, market", bn: "বার্ষিক, বাজার" }, g.bt_ann_bench ?? 0, c.bt_ann_bench ?? 0],
                        ] : []),
                      ].map(([lab, a, b]) => (
                        <tr key={(lab as { en: string }).en}><td><L p={lab as { en: string; bn: string }} /></td><td className="r num">{P(a as number, 1, (lab as { en: string }).en !== "Average turnover")}</td><td className="r num">{P(b as number, 1, (lab as { en: string }).en !== "Average turnover")}</td></tr>
                      ))}
                      {(g.bt_years ?? 0) >= 1 && (
                        <tr><td><L en="Information ratio vs market" bn="ইনফরমেশন রেশিও" /></td><td className="r num-en">{(g.bt_info_ratio_net ?? 0).toFixed(2)}</td><td className="r num-en">{(c.bt_info_ratio_net ?? 0).toFixed(2)}</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <p className="note">{g.bt_years ? `${g.bt_years.toFixed(1)} years out of sample. ` : ""}Top decile, rebalanced every {m.config.horizon} sessions, entry at next open, {pct(m.config.roundTripCost, 2).en} round-trip cost ({m.config.commissionBps} bps commission + {m.config.slippageBps} bps slippage per side).</p>
              </section>
            </div>

            <div className="row">
              <section className="card" aria-label="Walk-forward">
                <div className="card-head"><h2><L en="How it was tested" bn="কীভাবে পরীক্ষা করা হয়েছে" /> <span className="en-inline">· purged walk-forward</span></h2>
                  <span className="legend"><span><span className="sw" style={{ background: "#0F3A2C" }} />Train</span><span><span className="sw purge" style={{ border: "1px solid #9DB5A8" }} />Purged</span><span><span className="sw" style={{ background: "#262B6B" }} />Test</span></span></div>
                <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                  {(m.folds.length > 12 ? Array.from({ length: 12 }, (_, i) => m.folds[Math.round((i * (m.folds.length - 1)) / 11)]) : m.folds).map((f) => {
                    const a = 0, b = (days(t0!, f.train_end) / span) * 100, ts = (days(t0!, f.test_start) / span) * 100, te = (days(t0!, f.test_end) / span) * 100;
                    return (
                      <div key={f.fold} style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr)", gap: 12, alignItems: "center" }} title={`Train ${f.train_start} to ${f.train_end} (${f.train_rows} rows), test ${f.test_start} to ${f.test_end}`}>
                        <span className="en muted" style={{ fontSize: 13 }}>Fold {f.fold + 1}</span>
                        <span style={{ height: 14, position: "relative", background: "var(--ground)" }}>
                          <span style={{ position: "absolute", left: `${a}%`, width: `${b - a}%`, top: 0, bottom: 0, background: "#0F3A2C" }} />
                          <span className="purge" style={{ position: "absolute", left: `${b}%`, width: `${ts - b}%`, top: 0, bottom: 0 }} />
                          <span style={{ position: "absolute", left: `${ts}%`, width: `${Math.max(1, te - ts)}%`, top: 0, bottom: 0, background: "#262B6B" }} />
                        </span>
                      </div>
                    );
                  })}
                  <div style={{ display: "grid", gridTemplateColumns: "64px minmax(0,1fr)", gap: 12 }}><span /><span className="axis" style={{ paddingTop: 0 }}><span><V p={dateLabel(t0!)} /></span><span><V p={dateLabel(t1!)} /></span></span></div>
                </div>
                <p className="note">{m.folds.length > 12 && <span className="en">{m.folds.length} folds in total, 12 shown. </span>}<L en="Training rows whose label window reaches the test block are removed, so no future return leaks into training." bn="যে প্রশিক্ষণ সারির রিটার্ন-জানালা পরীক্ষার সময়ে পৌঁছায়, তা বাদ দেওয়া হয়, তাই ভবিষ্যতের তথ্য ফাঁস হয় না।" /></p>
              </section>

              <section className="card" aria-label="Feature families">
                <div className="card-head"><h2><L en="What the model leans on" bn="মডেল কীসের ওপর নির্ভর করে" /></h2><span className="en muted" style={{ fontSize: 12 }}>Share of mean |SHAP|</span></div>
                {(() => {
                  const e = Object.entries(m.familyImportance).sort((a, b) => b[1] - a[1]);
                  const tot = e.reduce((s, [, v]) => s + v, 0);
                  const mx = e[0]?.[1] ?? 1;
                  return (
                    <div style={{ marginTop: 12 }}>
                      {e.map(([k, v]) => (
                        <div key={k} style={{ display: "grid", gridTemplateColumns: "minmax(0,170px) minmax(0,1fr) 48px", gap: 12, alignItems: "center", padding: "8px 0", borderTop: "1px solid var(--rule)" }}>
                          <span style={{ fontSize: 14 }}><L p={FAMILY[k] ?? { en: k, bn: k }} /></span>
                          <span style={{ height: 10, background: "var(--ground)" }}><span style={{ display: "block", height: "100%", width: `${(v / mx) * 100}%`, background: "#262B6B" }} /></span>
                          <span className="num" style={{ textAlign: "right", fontSize: 14 }}><V p={pct(v / tot, 0)} /></span>
                        </div>
                      ))}
                    </div>
                  );
                })()}
                <p className="note">Validated on data from {dateLabel(m.quality.start).en} to {dateLabel(m.quality.end).en} ({m.quality.trading_days} sessions). Every metric has wide error bars until more history is loaded.</p>
              </section>
            </div>
          </>
        )}
      </div>
    </>
  );
}
