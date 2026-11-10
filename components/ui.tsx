"use client";
import type { ReactNode } from "react";
import { L, V } from "@/components/lang";
import { SIGNAL } from "@/lib/i18n";

export function SignalChip({ s }: { s: string }) {
  // Chips carry one language: Bangla in bilingual mode (the column header pairs it with English).
  return <span className={`chip chip-${s}`}><V p={{ en: SIGNAL[s].en, bn: SIGNAL[s].bn }} /></span>;
}

export function ScoreBar({ score, max = 0.5 }: { score: number; max?: number }) {
  const w = Math.min(50, (Math.abs(score) / max) * 50);
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span className="sbar" aria-hidden="true">
        <i className={score >= 0 ? "p" : "n"} style={{ width: `${w}%` }} />
        <b />
      </span>
      <span className="num-en num" style={{ fontSize: 14 }}>{score >= 0 ? "+" : "−"}{Math.abs(score).toFixed(3)}</span>
    </span>
  );
}

export function PageHead({ crumb, title, lede, actions }: { crumb?: ReactNode; title: ReactNode; lede?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head gl">
      <div>
        {crumb && <div className="crumb">{crumb}</div>}
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
      </div>
      {actions && <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>{actions}</div>}
    </header>
  );
}

export function Loading({ h = 200 }: { h?: number }) {
  return <div className="skeleton" style={{ height: h }} aria-label="Loading" />;
}

export function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="err" role="alert">
      <L en="Could not load data from the API." bn="এপিআই থেকে তথ্য আনা যায়নি।" /> <span className="en">{msg}</span>
    </div>
  );
}
