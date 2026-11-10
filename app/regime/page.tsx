"use client";
import { LineChart } from "@/components/charts";
import { L, V, useLang } from "@/components/lang";
import { ErrorBox, Loading, PageHead } from "@/components/ui";
import { useApi } from "@/lib/api";
import { dateLabel, pct, toBn } from "@/lib/i18n";

type Regime = {
  threshold: number;
  current: { breadth_20: number; mkt_ret_10: number; risk_off: boolean };
  series: { date: string; breadth: number | null; mkt10: number | null; riskOff: boolean }[];
};

export default function RegimePage() {
  const { lang } = useLang();
  const { data, error } = useApi<Regime>("/regime");
  if (error) return <><PageHead title="Market regime" /><div className="content"><ErrorBox msg={error} /></div></>;
  const s = data?.series ?? [];
  const labels = s.map((d) => (lang === "bi" ? dateLabel(d.date).bn : dateLabel(d.date).en));
  const offDays = s.filter((d) => d.riskOff).length;

  return (
    <>
      <PageHead crumb={<L en="Market-wide conditions" bn="সামগ্রিক বাজার" />}
        title={data ? (data.current.risk_off ? <L en="The market is in risk-off mode" bn="বাজার এখন ঝুঁকি-এড়ানো অবস্থায়" /> : <L en="The market is in normal mode" bn="বাজার এখন স্বাভাবিক অবস্থায়" />) : <L en="Market regime" bn="বাজার পরিস্থিতি" />}
        lede="Breadth and trend decide how strict the Buy list is." />
      <div className="content">
        {!data ? <Loading h={360} /> : (
          <>
            <section className="tiles">
              <div className="tile"><div className="k"><L en="Stocks above 20-day average" bn="২০ দিনের গড়ের ওপরে শেয়ার" stack /></div><div className="v" style={{ color: data.current.breadth_20 < data.threshold ? "var(--crimson-ink)" : "var(--pos-ink)" }}><V p={pct(data.current.breadth_20, 0)} /></div><div className="s">Risk-off line at {Math.round(data.threshold * 100)}%</div></div>
              <div className="tile"><div className="k"><L en="Market, last 10 sessions" bn="বাজার, শেষ ১০ সেশন" stack /></div><div className="v"><V p={pct(data.current.mkt_ret_10, 1, true)} /></div><div className="s">Equal-weight average of all equities</div></div>
              <div className="tile"><div className="k"><L en="Risk-off sessions" bn="ঝুঁকি-এড়ানো সেশন" stack /></div><div className="v"><V p={{ en: `${offDays} / ${s.length}`, bn: toBn(`${offDays} / ${s.length}`) }} /></div><div className="s">In the stored history</div></div>
            </section>
            <section className="card">
              <div className="card-head"><h2><L en="Market breadth" bn="বাজারের বিস্তৃতি" /></h2>
                <span className="legend"><span><span className="sw" style={{ height: 2, background: "#262B6B" }} />% above 20-day avg</span><span><span className="sw" style={{ background: "#FBEFF3", border: "1px solid #EBB8C9" }} />Risk-off session</span></span></div>
              <div style={{ marginTop: 12 }}>
                <LineChart ariaLabel="Share of stocks above their 20-day average over time" labels={labels} height={240}
                  yFmt={(v) => `${Math.round(v)}%`} refLine={data.threshold * 100} refLabel="risk-off line"
                  shade={s.map((d) => d.riskOff)}
                  series={[{ name: "Above 20-day avg", color: "#262B6B", values: s.map((d) => (d.breadth == null ? null : d.breadth * 100)) }]} />
              </div>
              <p className="note"><L en="Risk-off = breadth below the line AND the market down over 10 sessions. In risk-off, only the top 5% of scores become Buy calls instead of the top 10%." bn="ঝুঁকি-এড়ানো = বিস্তৃতি রেখার নিচে এবং ১০ সেশনে বাজার নিম্নমুখী। তখন শীর্ষ ১০%-এর বদলে শুধু শীর্ষ ৫% কেনার তালিকায় আসে।" /></p>
            </section>
            <section className="card">
              <div className="card-head"><h2><L en="Market return, rolling 10 sessions" bn="বাজারের রিটার্ন, ১০ সেশন" /></h2></div>
              <div style={{ marginTop: 12 }}>
                <LineChart ariaLabel="Rolling 10-session equal-weight market return" labels={labels} height={200}
                  yFmt={(v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%`} refLine={0}
                  series={[{ name: "Market 10-session", color: "#1F7A55", values: s.map((d) => (d.mkt10 == null ? null : d.mkt10 * 100)) }]} />
              </div>
            </section>
          </>
        )}
      </div>
    </>
  );
}
