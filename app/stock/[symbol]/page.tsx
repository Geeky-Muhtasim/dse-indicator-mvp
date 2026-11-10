"use client";
import Link from "next/link";
import { use, useEffect, useMemo, useRef, useState } from "react";
import { LineChart, VolumeBars } from "@/components/charts";
import { L, V, useLang } from "@/components/lang";
import { ErrorBox, Loading, PageHead, SignalChip } from "@/components/ui";
import { api, useApi, type Driver, type Explanation, type Placement, type SignalRow } from "@/lib/api";
import { FAMILY, SIGNAL, dateLabel, describe, money, pct, toBn } from "@/lib/i18n";

type StockResp = {
  asof: string; signal: SignalRow; history: (string | number | null)[][]; historyCols: string[];
  features: Record<string, number>; explanation: Explanation; families: Record<string, string>;
  ranges: Record<string, [number, number]>; computeMs: number;
};
type ScoreResp = Explanation & { placement: Placement; computeMs: number };

// Inputs exposed in the what-if panel, with how to show them to a person.
const KNOBS: { f: string; en: string; bn: string; min: number; max: number; step: number; show: (v: number) => string; toUi?: (v: number) => number; fromUi?: (u: number) => number }[] = [
  { f: "range_pos_20", en: "Position in 20-day range", bn: "২০ দিনের সীমায় অবস্থান", min: 0, max: 1, step: 0.01, show: (v) => `${Math.round(v * 100)}%` },
  { f: "rs_rank_20", en: "20-day strength vs market", bn: "২০ দিনে বাজারের তুলনায় শক্তি", min: 0, max: 1, step: 0.01, show: (v) => `${Math.round(v * 100)}th pct` },
  { f: "rsi_14", en: "RSI 14", bn: "আরএসআই ১৪", min: 5, max: 95, step: 1, show: (v) => v.toFixed(0) },
  { f: "rel_volume", en: "Volume vs 20-day median", bn: "২০ দিনের মধ্যমার তুলনায় লেনদেন", min: Math.log(0.2), max: Math.log(5), step: 0.01, show: (v) => `${Math.exp(v).toFixed(2)}x` },
];

export default function StockPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params);
  const sym = decodeURIComponent(symbol).toUpperCase();
  const { lang } = useLang();
  const { data, error } = useApi<StockResp>(`/stock/${encodeURIComponent(sym)}`);
  const [over, setOver] = useState<Record<string, number>>({});
  const [live, setLive] = useState<ScoreResp | null>(null);
  const [busy, setBusy] = useState(false);
  const [liveErr, setLiveErr] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { setOver({}); setLive(null); }, [sym]);

  // Re-score through the backend whenever a what-if input changes (debounced).
  useEffect(() => {
    if (!data || Object.keys(over).length === 0) { setLive(null); return; }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setBusy(true);
      setLiveErr(null);
      try {
        const r = await api<ScoreResp>("/score", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol: sym, overrides: over }) });
        setLive(r);
      } catch (e) {
        setLiveErr(String((e as Error).message));
      } finally {
        setBusy(false);
      }
    }, 250);
  }, [over, data, sym]);

  const ex = live ?? data?.explanation;
  const rows = useMemo(() => {
    if (!ex) return [];
    const c = [...ex.contributions];
    const top = c.slice(0, 7);
    const rest = c.slice(7);
    return { top, restSum: rest.reduce((a, d) => a + d.shap, 0), restN: rest.length };
  }, [ex]) as { top: Driver[]; restSum: number; restN: number } | [];

  if (error) return <><PageHead title={sym} /><div className="content"><ErrorBox msg={error} /></div></>;

  const s = data?.signal;
  const hist = data?.history ?? [];
  const col = (k: string) => data ? data.historyCols.indexOf(k) : -1;
  const labels = hist.map((h) => (lang === "bi" ? dateLabel(String(h[0])).bn : dateLabel(String(h[0])).en));
  const closes = hist.map((h) => h[col("close")] as number);
  const ma = hist.map((h) => h[col("ma20")] as number | null);
  const vols = hist.map((h) => h[col("volume")] as number);
  const maxAbs = ex ? Math.max(...ex.contributions.map((d) => Math.abs(d.shap)), Math.abs((rows as { restSum: number }).restSum ?? 0)) : 1;
  const place = live?.placement;
  const sigNow = place?.signal ?? s?.signal ?? "HOLD";
  const lc = (t?: string) => (t && !/^[A-Z]{2}/.test(t) ? t[0].toLowerCase() + t.slice(1) : t ?? "");

  const Contrib = ({ d }: { d: Driver }) => {
    const t = describe(d.feature, d.value);
    const fam = FAMILY[data?.families[d.feature] ?? ""] ?? { en: "", bn: "" };
    const w = (Math.abs(d.shap) / maxAbs) * 50;
    return (
      <div className="contrib">
        <span style={{ lineHeight: 1.3 }}><L p={t} stack /></span>
        <span className="fam sub"><L p={fam} /></span>
        <span className="track"><b /><i className={d.shap >= 0 ? "p" : "n"} style={{ width: `${w}%` }} /></span>
        <span className="val" style={{ color: d.shap >= 0 ? "var(--pos-ink)" : "var(--crimson-ink)", fontWeight: 600 }}>{d.shap >= 0 ? "+" : "−"}{Math.abs(d.shap).toFixed(3)}</span>
      </div>
    );
  };

  const forTxt = s?.for[0] ? describe(s.for[0].feature, s.for[0].value) : null;
  const forTxt2 = s?.for[1] ? describe(s.for[1].feature, s.for[1].value) : null;
  const agTxt = s?.against[0] ? describe(s.against[0].feature, s.against[0].value) : null;

  return (
    <>
      <PageHead
        crumb={<><Link href="/"><L en="Today's signals" bn="আজকের সংকেত" /></Link> › <L en="Stock analysis" bn="শেয়ার বিশ্লেষণ" /> {data && <span className="en"> · data to {dateLabel(data.asof).en}</span>}</>}
        title={
          <span style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
            <span className="en" style={{ fontSize: 44, lineHeight: 1.1 }}>{sym}</span>
            {s && <span className="num" style={{ fontSize: 28, color: "var(--indigo)" }}><V p={money(s.close)} /></span>}
            {s && s.chg1d != null && <span className={`num ${s.chg1d > 0 ? "up" : s.chg1d < 0 ? "down" : "muted"}`} style={{ fontSize: 16, fontWeight: 500 }}>{s.chg1d > 0 ? "▲" : s.chg1d < 0 ? "▼" : ""} <V p={pct(Math.abs(s.chg1d), 2)} /></span>}
          </span>
        }
        actions={s && (
          <span className={`chip chip-${s.signal}`} style={{ flexDirection: "column", minHeight: 56, padding: "6px 18px", justifyContent: "center", fontSize: 22, border: "1.5px solid currentColor", borderRadius: 6 }}>
            <V p={SIGNAL[s.signal]} />
            <span className="sub" style={{ color: "inherit", fontSize: 12 }}>rank {s.rank} today</span>
          </span>
        )}
      />
      <div className="content">
        <section className="tiles" aria-label="Key figures">
          {s ? (
            <>
              <div className="tile"><div className="k"><L en="Model score" bn="মডেল স্কোর" stack /></div><div className="v num-en">{s.score >= 0 ? "+" : "−"}{Math.abs(s.score).toFixed(3)}</div><div className="s">−1 to +1, the average stock is 0</div></div>
              <div className="tile gl" style={{ backgroundColor: "var(--panel)" }}><div className="k"><L en="Odds of beating the market" bn="আস্থা" stack /></div><div className="v" style={{ color: "var(--indigo)" }}><V p={pct(s.odds, 0)} /></div><div className="s">Decile {s.decile}, out of sample, next 5 sessions</div></div>
              <div className="tile"><div className="k"><L en="Mean excess return" bn="গড় অতিরিক্ত রিটার্ন" stack /></div><div className="v"><V p={pct(s.meanExcess, 2, true)} /></div><div className="s">Same decile, per 5 sessions, before costs</div></div>
              <div className="tile"><div className="k"><L en="Rank today" bn="আজকের ক্রম" stack /></div><div className="v"><V p={{ en: String(s.rank), bn: toBn(String(s.rank)) }} /></div><div className="s">Top {Math.max(1, Math.ceil((1 - s.pct) * 100))}% of the universe</div></div>
            </>
          ) : [0, 1, 2, 3].map((i) => <Loading key={i} h={118} />)}
        </section>

        <div className="row" style={{ alignItems: "flex-start" }}>
          <section className="card" style={{ flex: "3 1 520px" }} aria-label="Price">
            <div className="card-head">
              <h2><L en="Price and volume" bn="দর ও লেনদেন" /> <span className="en-inline">· last {hist.length} sessions</span></h2>
              <span className="legend"><span><span className="sw" style={{ height: 2, background: "#262B6B" }} />Close</span><span><span className="sw" style={{ height: 0, borderTop: "2px dashed #4A6458" }} />20-day average</span></span>
            </div>
            {data ? (
              <div style={{ marginTop: 12 }}>
                <LineChart ariaLabel={`${sym} closing price over ${hist.length} sessions`} labels={labels}
                  series={[{ name: "20-day avg", color: "#4A6458", dash: "5 4", values: ma }, { name: "Close", color: "#262B6B", values: closes }]} />
                <VolumeBars values={vols} />
              </div>
            ) : <Loading h={260} />}
          </section>

          <section className="card gl" style={{ flex: "2 1 320px", backgroundColor: "var(--panel)", display: "flex", flexDirection: "column", gap: 14 }} aria-label="What-if">
            <div>
              <h2><L en="What-if, scored live" bn="যদি এমন হয়" /></h2>
              <p className="note" style={{ marginTop: 4 }}><L en="Move an input: the backend re-scores and re-explains this stock with the same model." bn="একটি মান বদলান, ব্যাকএন্ড একই মডেলে নতুন স্কোর ও কারণ দেবে।" /></p>
            </div>
            {data && KNOBS.map((k) => {
              const v = over[k.f] ?? data.features[k.f];
              return (
                <div className="slider" key={k.f}>
                  <label htmlFor={`k-${k.f}`}><span><L en={k.en} bn={k.bn} /></span><span className="num-en">{k.show(v)}</span></label>
                  <input id={`k-${k.f}`} type="range" min={k.min} max={k.max} step={k.step} value={v}
                    onChange={(e) => setOver((o) => ({ ...o, [k.f]: parseFloat(e.target.value) }))} />
                </div>
              );
            })}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", borderTop: "1px solid var(--rule)", paddingTop: 12 }}>
              <span style={{ lineHeight: 1.3 }}>
                <span style={{ fontSize: 13, color: "var(--muted)" }}>{live ? <L en="What-if score" bn="নতুন স্কোর" /> : <L en="Current score" bn="বর্তমান স্কোর" />}</span>
                <span className="num-en" style={{ display: "block", fontSize: 22, fontWeight: 600 }}>
                  {ex ? `${ex.score >= 0 ? "+" : "−"}${Math.abs(ex.score).toFixed(3)}` : "…"} {busy && <span className="muted" style={{ fontSize: 13 }}>scoring…</span>}
                </span>
                {place && <span style={{ fontSize: 13 }}><SignalChip s={place.signal} /> <span className="en muted">rank {place.rank} of {place.of} · odds {pct(place.odds, 0).en}</span></span>}
              </span>
              <button type="button" className="btn btn-ghost" onClick={() => setOver({})} disabled={!Object.keys(over).length}><L en="Reset" bn="আগের মানে ফিরুন" stack /></button>
            </div>
            {liveErr && <span className="down" style={{ fontSize: 13 }}>{liveErr}</span>}
            <span className="en muted" style={{ fontSize: 12 }}>POST /api/score · pure-Python TreeSHAP over {data ? "the exported LightGBM trees" : "…"}{live ? ` · ${live.computeMs} ms` : ""}</span>
          </section>
        </div>

        <section className="card" aria-label="Why">
          <div className="card-head">
            <h2>{sigNow === "AVOID" ? <L en="Why Avoid" bn="কেন এড়িয়ে চলুন?" /> : sigNow === "BUY" ? <L en="Why Buy" bn="কেন কিনুন?" /> : <L en="Why Hold" bn="কেন ধরে রাখুন?" />} <span className="en-inline">· how each input moved the score</span></h2>
            <span className="en muted" style={{ fontSize: 12 }}>SHAP contributions add up to the score{live ? " (what-if)" : ""}</span>
          </div>
          {ex && !Array.isArray(rows) ? (
            <div style={{ marginTop: 12 }}>
              <div className="contrib">
                <span style={{ lineHeight: 1.3 }}><L en="Starting point: the average stock" bn="গড় শেয়ারের ভিত্তি মান" stack /></span>
                <span className="fam sub">Base</span>
                <span className="track"><b /><i className="z" style={{ width: `${(Math.abs(ex.base) / maxAbs) * 50}%` }} /></span>
                <span className="val">{ex.base >= 0 ? "+" : "−"}{Math.abs(ex.base).toFixed(3)}</span>
              </div>
              {rows.top.map((d) => <Contrib key={d.feature} d={d} />)}
              <div className="contrib">
                <span style={{ lineHeight: 1.3 }}><L en={`${rows.restN} more features, combined`} bn={`আরও ${toBn(String(rows.restN))}টি বৈশিষ্ট্য, মিলিয়ে`} stack /></span>
                <span className="fam sub"><L en="Mixed" bn="মিশ্র" /></span>
                <span className="track"><b /><i className={rows.restSum >= 0 ? "z" : "n"} style={{ width: `${(Math.abs(rows.restSum) / maxAbs) * 50}%`, ...(rows.restSum < 0 ? {} : {}) }} /></span>
                <span className="val">{rows.restSum >= 0 ? "+" : "−"}{Math.abs(rows.restSum).toFixed(3)}</span>
              </div>
              <div className="contrib total">
                <span><L en="Final score" bn="চূড়ান্ত স্কোর" /></span><span /><span />
                <span className="val" style={{ fontSize: 17 }}>{ex.score >= 0 ? "+" : "−"}{Math.abs(ex.score).toFixed(3)}</span>
              </div>
            </div>
          ) : <Loading h={320} />}

          {s && forTxt && !live && (
            <div className="gd" style={{ marginTop: 14, borderRadius: 8, padding: "16px 20px", color: "#F8FAF7", lineHeight: 1.45 }}>
              {lang === "bi" && (
                <div style={{ fontSize: 18, fontWeight: 500 }}>
                  {s.signal === "AVOID" ? "নিচের দিকে থাকার কারণ" : "শীর্ষে থাকার কারণ"}: {(s.signal === "AVOID" ? (agTxt?.bn ?? "") : forTxt.bn)}{s.signal !== "AVOID" && forTxt2 ? `; ${forTxt2.bn}` : ""}। {s.signal !== "AVOID" && agTxt ? `বিপক্ষে: ${agTxt.bn}।` : ""}
                </div>
              )}
              <div className="en" style={{ fontSize: lang === "bi" ? 14 : 18, color: lang === "bi" ? "#B9CEC2" : "#F8FAF7", marginTop: lang === "bi" ? 4 : 0 }}>
                {s.signal === "AVOID" ? "Ranks near the bottom" : s.signal === "BUY" ? "Ranks near the top" : "Mid-pack"}: {lc(s.signal === "AVOID" ? agTxt?.en : forTxt.en)}{s.signal !== "AVOID" && forTxt2 ? `; ${lc(forTxt2.en)}` : ""}.{s.signal !== "AVOID" && agTxt ? ` Against it: ${lc(agTxt.en)}.` : ""} Built only from the contributions above. Not investment advice.
              </div>
            </div>
          )}
          {live && <p className="note"><L en="Showing the what-if explanation. Reset to see today's actual call." bn="যদি-এমন-হয় ব্যাখ্যা দেখাচ্ছে। আজকের প্রকৃত সংকেত দেখতে রিসেট করুন।" /></p>}
        </section>
      </div>
    </>
  );
}
