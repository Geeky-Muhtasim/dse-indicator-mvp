"use client";
import { L } from "@/components/lang";
import { PageHead } from "@/components/ui";
import { useApi, type Meta } from "@/lib/api";

const STEPS: { en: string; bn: string; body: string }[] = [
  { en: "Data", bn: "তথ্য", body: "End-of-day prices for every DSE instrument. History comes from an adjusted StockNow export; each trading day after the close a scheduled job pulls the new session from dsebd.org. When DSE's reported previous close differs from the stored close (a bonus or rights issue), the whole history of that stock is rescaled so the series stays continuous." },
  { en: "Universe", bn: "শেয়ারের তালিকা", body: "Ordinary shares only: mutual funds and bonds are removed. The least liquid 20% by 20-day median turnover are dropped, recomputed every day using only what was known that day." },
  { en: "Features", bn: "বৈশিষ্ট্য", body: "19 point-in-time features in six families: momentum (returns, RSI, MACD), trend (moving-average gaps and slope, range position), volatility (ATR, Bollinger width, volatility ratio), volume (relative volume, OBV, liquidity), relative strength (return rank against the market) and market regime (breadth, market return). A test checks that deleting future data never changes a past feature." },
  { en: "Target", bn: "লক্ষ্য", body: "The return from the next session's open to the close five sessions later, minus the equal-weight market, ranked across stocks. Ranking removes the market's direction so the model learns which stocks to favour, not when to be in the market." },
  { en: "Models", bn: "মডেল", body: "A transparent five-factor scorecard with no fitting is the baseline. The main model is LightGBM regression on the rank target. It is only promoted after retraining if its out-of-sample rank IC is above zero." },
  { en: "Validation", bn: "যাচাই", body: "Expanding walk-forward: train on the past, test on the next block, roll forward. Training rows whose label window reaches the test block are purged. The backtest uses the next open for entry, skips stocks locked at a price limit, and charges commission and slippage on turnover." },
  { en: "Signals", bn: "সংকেত", body: "Top 10% of scores are Buy (top 5% when the market is risk-off), bottom 20% Avoid, the rest Hold. There is no Sell call because retail investors on DSE cannot short. The odds shown are the out-of-sample hit rate of the stock's score decile." },
  { en: "Explanations", bn: "ব্যাখ্যা", body: "Each score is split into per-feature SHAP contributions that add up exactly to the score. The API recomputes them live with a pure-Python TreeSHAP over the exported trees, checked against LightGBM's own output to within 1e-15. Every sentence of rationale is generated from those contributions, so it cannot invent a reason." },
];

export default function MethodPage() {
  const { data: m } = useApi<Meta>("/meta");
  return (
    <>
      <PageHead crumb={<L en="How it works" bn="কীভাবে কাজ করে" />} title={<L en="Method and limits" bn="পদ্ধতি ও সীমাবদ্ধতা" />}
        lede="A research tool that ranks stocks and shows its working. Not investment advice." />
      <div className="content prose">
        <section className="card">
          {STEPS.map((s, i) => (
            <div key={s.en} style={{ display: "grid", gridTemplateColumns: "36px minmax(0,1fr)", gap: 12, padding: "12px 0", borderTop: i ? "1px solid var(--rule)" : undefined }}>
              <span className="num" style={{ fontWeight: 600, color: "var(--indigo)" }}>{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3 style={{ margin: 0 }}><L en={s.en} bn={s.bn} /></h3>
                <p className="en" style={{ margin: "4px 0 0", color: "var(--muted)" }}>{s.body}</p>
              </div>
            </div>
          ))}
        </section>
        <section className="card">
          <h2><L en="Limits" bn="সীমাবদ্ধতা" /></h2>
          <ul className="en" style={{ color: "var(--muted)", margin: "8px 0 0", paddingLeft: 20 }}>
            <li>The first model was validated on about 60 sessions in one falling market. Treat every metric as provisional until years of history are loaded.</li>
            <li>Cost assumptions (35 bps commission and 10 bps slippage per side) are estimates.</li>
            <li>No dividends, sectors or fundamentals yet.</li>
            <li>Prices are public end-of-day data from the Dhaka Stock Exchange, shown here for research. Live intraday data is licensed and not used.</li>
          </ul>
          {m && <p className="en" style={{ color: "var(--muted)", fontSize: 13, marginTop: 12 }}>Source: {m.source}. Last generated {m.generatedAt.replace("T", " ").replace("+00:00", " UTC")}.</p>}
        </section>
      </div>
    </>
  );
}
