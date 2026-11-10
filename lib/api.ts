"use client";
import { useEffect, useState } from "react";

export type Driver = { feature: string; value: number; shap: number };
export type SignalRow = {
  symbol: string; close: number; chg1d: number | null; signal: "BUY" | "HOLD" | "AVOID" | "NR";
  score: number; rank: number; pct: number; decile: number; odds: number | null;
  meanExcess: number | null; fillRisk: boolean; for: Driver[]; against: Driver[];
  // only on not-rated rows
  reason?: "illiquid" | "new" | "not_traded" | "incomplete"; lastTraded?: string; medTurnover?: number | null;
};
export type Meta = {
  asof: string; generatedAt: string; universe: number;
  counts: { BUY: number; HOLD: number; AVOID: number; NR?: number };
  unratedReasons?: Record<string, number>; liquidityCut?: number | null;
  regime: { breadth_20: number; mkt_ret_10: number; risk_off: boolean };
  horizon: number; roundTripCost: number; buyTopPct: number; avoidBottomPct: number;
  model: { version: string; trainedThrough: string; trainRows: number; oosIc: number; promoted: boolean };
  source: string;
};
export type Explanation = { score: number; base: number; contributions: Driver[] };
export type Placement = { pct: number; rank: number; of: number; signal: SignalRow["signal"]; decile: number; odds: number | null; meanExcess: number | null };

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, { cache: "no-store", ...init });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {}
    throw new Error(`${r.status}: ${detail}`);
  }
  return r.json();
}

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!path) return;
    let live = true;
    setError(null);
    api<T>(path).then((d) => live && setData(d)).catch((e) => live && setError(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, [path]);
  return { data, error, loading: !data && !error };
}
