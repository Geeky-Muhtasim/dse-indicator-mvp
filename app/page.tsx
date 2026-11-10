"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { L, V, useLang } from "@/components/lang";
import { ErrorBox, Loading, PageHead, ScoreBar, SignalChip } from "@/components/ui";
import { useApi, type Meta, type SignalRow } from "@/lib/api";
import { count, dateLabel, describe, money, pct, toBn } from "@/lib/i18n";

type Filter = "ALL" | "BUY" | "HOLD" | "AVOID";
const PAGE = 40;

export default function SignalsPage() {
  const { lang } = useLang();
  const router = useRouter();
  const meta = useApi<Meta>("/meta");
  const sig = useApi<{ asof: string; n: number; rows: SignalRow[] }>("/signals");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [q, setQ] = useState("");
  const [shown, setShown] = useState(PAGE);

  const rows = useMemo(() => {
    let r = sig.data?.rows ?? [];
    if (filter !== "ALL") r = r.filter((x) => x.signal === filter);
    if (q) r = r.filter((x) => x.symbol.includes(q.toUpperCase()));
    return r;
  }, [sig.data, filter, q]);

  const m = meta.data;
  const n = (x: number) => (lang === "bi" ? toBn(String(x)) : String(x));

  return (
    <>
      <PageHead
        crumb={m && <><V p={{ en: "Data as of", bn: "তথ্য:" }} /> <V p={dateLabel(m.asof, true)} /></>}
        title={m ? (
          lang === "bi"
            ? <>আজ {n(m.counts.BUY)}টি শেয়ার কেনার তালিকায়, {n(m.counts.AVOID)}টি এড়ানোর।</>
            : <>{m.counts.BUY} stocks rank as Buy today, {m.counts.AVOID} as Avoid.</>
        ) : <L en="Today's signals" bn="আজকের সংকেত" />}
        lede={m && `${m.counts.BUY} Buy, ${m.counts.HOLD} Hold and ${m.counts.AVOID} Avoid across ${m.universe} liquid DSE equities, ranked on the next ${m.horizon} sessions.`}
        actions={
          <>
            <a className="btn btn-ghost" href="/api/signals" download="dse-signals.json"><L en="Download data" bn="ডেটা নামান" stack /></a>
            <Link className="btn btn-primary" href="/evidence"><L en="How reliable is it?" bn="মডেল কতটা নির্ভরযোগ্য?" stack /></Link>
          </>
        }
      />
      <div className="content">
        {(meta.error || sig.error) && <ErrorBox msg={meta.error ?? sig.error ?? ""} />}

        {m && (m.regime.risk_off ? (
          <section className="alert" aria-label="Market regime">
            <span className="chip chip-solid"><V p={{ en: "Risk-off market", bn: "ঝুঁকি-এড়ানো বাজার" }} /></span>
            <span style={{ flex: "1 1 480px", lineHeight: 1.4 }}>
              <L stack
                 en={`Only ${Math.round(m.regime.breadth_20 * 100)}% of stocks are above their 20-day average and the market is ${pct(m.regime.mkt_ret_10, 1, true).en} over 10 days, so Buy is limited to the top ${Math.round(m.buyTopPct * 100)}%.`}
                 bn={toBn(`মাত্র ${Math.round(m.regime.breadth_20 * 100)}% শেয়ার ২০ দিনের গড়ের ওপরে, বাজার ১০ দিনে ${pct(m.regime.mkt_ret_10, 1, true).en}। কেনার সীমা শীর্ষ ${Math.round(m.buyTopPct * 100)}%-এ কড়া করা হয়েছে।`)} />
            </span>
            <Link href="/regime" style={{ color: "var(--crimson-ink)", fontSize: 13, fontWeight: 500 }}><L en="View regime" bn="বাজার দেখুন" /></Link>
          </section>
        ) : (
          <section className="okband" aria-label="Market regime">
            <span className="chip chip-BUY"><V p={{ en: "Normal market", bn: "স্বাভাবিক বাজার" }} /></span>
            <span><L en={`Buy is the top ${Math.round(m.buyTopPct * 100)}% of scores.`} bn={toBn(`শীর্ষ ${Math.round(m.buyTopPct * 100)}% স্কোর কেনার তালিকায়।`)} /></span>
          </section>
        ))}

        <section className="tiles" aria-label="Key figures">
          {m ? (
            <>
              <div className="tile"><div className="k"><L en="Buy calls" bn="কিনুন" stack /></div><div className="v" style={{ color: "var(--pos-ink)" }}><V p={count(m.counts.BUY)} /></div><div className="s">Top {Math.round(m.buyTopPct * 100)}% of scores</div></div>
              <div className="tile"><div className="k"><L en="Avoid calls" bn="এড়িয়ে চলুন" stack /></div><div className="v"><V p={count(m.counts.AVOID)} /></div><div className="s">Bottom {Math.round(m.avoidBottomPct * 100)}% of scores</div></div>
              <div className="tile gl" style={{ backgroundColor: "var(--panel)" }}><div className="k"><L en="Rank IC, out of sample" bn="র‍্যাঙ্ক আইসি" stack /></div><div className="v num-en" style={{ color: "var(--indigo)" }}>{m.model.oosIc.toFixed(3)}</div><div className="s">Above 0 means the ranking points the right way</div></div>
              <div className="tile"><div className="k"><L en="Model trained through" bn="মডেল প্রশিক্ষিত" stack /></div><div className="v" style={{ fontSize: 26 }}><V p={dateLabel(m.model.trainedThrough)} /></div><div className="s">{m.model.trainRows.toLocaleString()} labelled stock-days · v{m.model.version}</div></div>
            </>
          ) : [0, 1, 2, 3].map((i) => <Loading key={i} h={118} />)}
        </section>

        <section className="card" style={{ padding: 0, overflow: "hidden" }} aria-label="Signals">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 20px", flexWrap: "wrap", gap: 12 }}>
            <div className="seg" role="group" aria-label="Filter by signal">
              {(["ALL", "BUY", "HOLD", "AVOID"] as Filter[]).map((f) => {
                const c = f === "ALL" ? m?.universe : m?.counts[f];
                const lab = { ALL: { en: "All", bn: "সব" }, BUY: { en: "Buy", bn: "কিনুন" }, HOLD: { en: "Hold", bn: "ধরে রাখুন" }, AVOID: { en: "Avoid", bn: "এড়িয়ে চলুন" } }[f];
                return (
                  <button key={f} type="button" aria-pressed={filter === f} onClick={() => { setFilter(f); setShown(PAGE); }}>
                    {lang === "bi" ? lab.bn : lab.en} {c != null && <span className="num">{n(c)}</span>}
                  </button>
                );
              })}
            </div>
            <label className="search">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
              <span className="visually-hidden" style={{ position: "absolute", left: -9999 }}>Search ticker</span>
              <input value={q} onChange={(e) => { setQ(e.target.value); setShown(PAGE); }} placeholder={lang === "bi" ? "টিকার খুঁজুন · Ticker" : "Search ticker"} />
            </label>
          </div>
          <div className="tbl">
            <table style={{ minWidth: 920 }}>
              <thead>
                <tr>
                  <th style={{ width: 64 }}><L en="Rank" bn="ক্রম" /></th>
                  <th><L en="Ticker" bn="টিকার" /></th>
                  <th className="r"><L en="Close" bn="দর" /></th>
                  <th className="r"><L en="1 day" bn="১ দিন" /></th>
                  <th><L en="Signal" bn="সংকেত" /></th>
                  <th><L en="Score" bn="স্কোর" /></th>
                  <th className="r"><L en="Odds" bn="আস্থা" /></th>
                  <th><L en="Main driver" bn="প্রধান কারণ" /></th>
                </tr>
              </thead>
              <tbody>
                {sig.loading && <tr><td colSpan={8}><Loading h={300} /></td></tr>}
                {rows.slice(0, shown).map((r) => {
                  const main = r.signal === "AVOID" ? r.against[0] ?? r.for[0] : r.for[0] ?? r.against[0];
                  const d = main ? describe(main.feature, main.value) : null;
                  return (
                    <tr key={r.symbol} className="click" onClick={() => router.push(`/stock/${r.symbol}`)}>
                      <td className="num muted">{n(r.rank)}</td>
                      <td><Link className="tick" href={`/stock/${r.symbol}`} onClick={(e) => e.stopPropagation()}>{r.symbol}</Link>{r.fillRisk && <span className="sub down">limit move</span>}</td>
                      <td className="r price"><V p={money(r.close)} /></td>
                      <td className={`r num ${r.chg1d == null ? "" : r.chg1d > 0 ? "up" : r.chg1d < 0 ? "down" : "muted"}`}><V p={pct(r.chg1d, 2, true)} /></td>
                      <td><SignalChip s={r.signal} /></td>
                      <td><ScoreBar score={r.score} /></td>
                      <td className="r num" style={{ fontWeight: 500 }}><V p={pct(r.odds, 0)} /></td>
                      <td style={{ lineHeight: 1.35, minWidth: 260 }}>{d && <L p={d} stack />}</td>
                    </tr>
                  );
                })}
                {sig.data && rows.length === 0 && <tr><td colSpan={8} className="muted"><L en="No stocks match." bn="কোনো শেয়ার মেলেনি।" /></td></tr>}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", padding: "12px 20px 16px" }}>
            <p style={{ margin: 0, fontSize: 13, color: "var(--muted)", maxWidth: 760 }}>
              <L en={`Odds: how often stocks in this score decile beat the market over ${m?.horizon ?? 5} sessions, out of sample. Not investment advice.`}
                 bn="আস্থা: এই স্কোর দশমাংশের শেয়ার আউট-অব-স্যাম্পলে কতবার বাজারকে হারিয়েছে। বিনিয়োগ পরামর্শ নয়।" />
            </p>
            {rows.length > shown && (
              <button type="button" className="btn btn-ghost" onClick={() => setShown((s) => s + PAGE * 2)}>
                <L en={`Show more (${rows.length - shown} left)`} bn={toBn(`আরও দেখুন (${rows.length - shown}টি বাকি)`)} />
              </button>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
