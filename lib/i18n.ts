// English by default. "bi" mode puts Bangla first with English beneath, Foundry style.
export type Lang = "en" | "bi";

const BN_DIGITS = "০১২৩৪৫৬৭৮৯";
export const toBn = (s: string) => s.replace(/[0-9]/g, (d) => BN_DIGITS[+d]);

export type Pair = { en: string; bn: string };

export const SIGNAL: Record<string, Pair> = {
  BUY: { en: "Buy", bn: "কিনুন" },
  HOLD: { en: "Hold", bn: "ধরে রাখুন" },
  AVOID: { en: "Avoid", bn: "এড়িয়ে চলুন" },
  NR: { en: "Not rated", bn: "রেটিং নেই" },
};

/** Why a stock has no call, in both languages. */
export function reasonText(reason: string | undefined, medTurnover?: number | null, lastTraded?: string): Pair {
  switch (reason) {
    case "illiquid": {
      const lakh = medTurnover != null ? (medTurnover / 1e5).toFixed(1) : "?";
      return { en: `Illiquid: median turnover Tk ${lakh} lakh a day`, bn: toBn(`কম লেনদেন: দৈনিক মধ্যমা ৳ ${lakh} লাখ`) };
    }
    case "new":
      return { en: "Too little history (under 20 sessions)", bn: "পর্যাপ্ত ইতিহাস নেই (২০ সেশনের কম)" };
    case "not_traded":
      return { en: `No trade in the latest session (last ${lastTraded ?? "?"})`, bn: toBn(`সর্বশেষ সেশনে লেনদেন হয়নি (শেষ ${lastTraded ?? "?"})`) };
    default:
      return { en: "Not enough data to score", bn: "স্কোর করার মতো তথ্য নেই" };
  }
}

export const FAMILY: Record<string, Pair> = {
  Momentum: { en: "Momentum", bn: "গতি" },
  Trend: { en: "Trend", bn: "প্রবণতা" },
  Volatility: { en: "Volatility", bn: "অস্থিরতা" },
  Volume: { en: "Volume", bn: "লেনদেন" },
  "Relative strength": { en: "Relative strength", bn: "আপেক্ষিক শক্তি" },
  "Market regime": { en: "Market regime", bn: "বাজার পরিস্থিতি" },
};

const MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_BN = ["জানু", "ফেব্রু", "মার্চ", "এপ্রি", "মে", "জুন", "জুলা", "আগ", "সেপ্টে", "অক্টো", "নভে", "ডিসে"];
const DAYS_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAYS_BN = ["রবিবার", "সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার"];

export function dateLabel(iso: string, long = false): Pair {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const wd = dt.getUTCDay();
  return long
    ? { en: `${DAYS_EN[wd]} ${d} ${MONTHS_EN[m - 1]} ${y}`, bn: toBn(`${DAYS_BN[wd]}, ${d} ${MONTHS_BN[m - 1]} ${y}`) }
    : { en: `${d} ${MONTHS_EN[m - 1]}`, bn: toBn(`${d} ${MONTHS_BN[m - 1]}`) };
}

const pctStr = (x: number, d = 1, sign = false) =>
  `${sign && x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(d)}%`;

export function pct(x: number | null | undefined, d = 1, sign = false): Pair {
  if (x == null || !isFinite(x)) return { en: "n/a", bn: "প্রযোজ্য নয়" };
  const s = pctStr(x, d, sign);
  return { en: s, bn: toBn(s) };
}

export function money(x: number | null | undefined): Pair {
  if (x == null) return { en: "n/a", bn: "প্রযোজ্য নয়" };
  const en = `Tk ${x.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  // South Asian grouping for Bangla: 2,618.30 stays, 12,50,000.00 for lakhs.
  const bn = "৳ " + toBn(x.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  return { en, bn };
}

export function count(n: number): Pair {
  return { en: n.toLocaleString("en-US"), bn: toBn(n.toLocaleString("en-IN")) };
}

/** Plain-language driver text for a feature value, in both languages. */
export function describe(feature: string, v: number): Pair {
  const n = feature.split("_").pop() ?? "";
  const ex = Math.expm1(v);
  let p: Pair;
  switch (feature) {
    case "rs_rank_10":
    case "rs_rank_20":
      p = { en: `${n}-day return beats ${Math.round(v * 100)}% of the market`, bn: `${n} দিনের রিটার্ন বাজারের ${Math.round(v * 100)}%-এর চেয়ে ভালো` };
      break;
    case "ret_5":
    case "ret_10":
    case "ret_20":
      p = { en: `${feature.split("_")[1]}-day return ${pctStr(ex, 1, true)}`, bn: `${feature.split("_")[1]} দিনের রিটার্ন ${pctStr(ex, 1, true)}` };
      break;
    case "rsi_14": {
      const r = Math.round(v);
      const en = r >= 70 ? " (overbought)" : r <= 30 ? " (oversold)" : "";
      const bn = r >= 70 ? " (অতিকেনা)" : r <= 30 ? " (অতিবিক্রি)" : "";
      p = { en: `RSI ${r}${en}`, bn: `আরএসআই ${r}${bn}` };
      break;
    }
    case "macd_hist":
      p = v > 0 ? { en: "MACD momentum turning up", bn: "এমএসিডি গতি ঊর্ধ্বমুখী" } : { en: "MACD momentum turning down", bn: "এমএসিডি গতি নিম্নমুখী" };
      break;
    case "ma_gap_10":
    case "ma_gap_20": {
      const a = Math.abs(v * 100).toFixed(1);
      p = v >= 0
        ? { en: `Price ${a}% above its ${n}-day average`, bn: `${n} দিনের গড়ের ${a}% ওপরে দর` }
        : { en: `Price ${a}% below its ${n}-day average`, bn: `${n} দিনের গড়ের ${a}% নিচে দর` };
      break;
    }
    case "ma_slope_10": {
      const a = Math.abs(v * 100).toFixed(1);
      p = v >= 0
        ? { en: `10-day average rising ${a}% in a week`, bn: `১০ দিনের গড় এক সপ্তাহে ${a}% বেড়েছে` }
        : { en: `10-day average falling ${a}% in a week`, bn: `১০ দিনের গড় এক সপ্তাহে ${a}% কমেছে` };
      break;
    }
    case "range_pos_20":
      p = { en: `Price at ${Math.round(v * 100)}% of its 20-day range`, bn: `২০ দিনের সীমার ${Math.round(v * 100)}% উচ্চতায় দর` };
      break;
    case "atr_pct_14":
      p = { en: `Average daily range ${(v * 100).toFixed(1)}% of price`, bn: `দৈনিক ওঠানামা দরের ${(v * 100).toFixed(1)}%` };
      break;
    case "bb_width_20":
      p = { en: `Bollinger band width ${(v * 100).toFixed(1)}%`, bn: `বলিঞ্জার ব্যান্ডের প্রস্থ ${(v * 100).toFixed(1)}%` };
      break;
    case "vol_ratio_5_20":
      p = { en: `Recent volatility ${v.toFixed(1)}x its 20-day level`, bn: `সাম্প্রতিক অস্থিরতা ২০ দিনের মাত্রার ${v.toFixed(1)} গুণ` };
      break;
    case "rel_volume":
      p = { en: `Volume ${Math.exp(v).toFixed(1)}x its 20-day median`, bn: `লেনদেনের পরিমাণ ২০ দিনের মধ্যমার ${Math.exp(v).toFixed(1)} গুণ` };
      break;
    case "obv_slope_10":
      p = v > 0 ? { en: "On-balance volume accumulating", bn: "ওবিভি: সংগ্রহ চলছে" } : { en: "On-balance volume distributing", bn: "ওবিভি: বিক্রির চাপ" };
      break;
    case "liquidity": {
      const tk = ex;
      p = { en: `Median turnover Tk ${(tk / 1e6).toFixed(1)} mn a day`, bn: `দৈনিক লেনদেন ৳ ${(tk / 1e5).toFixed(0)} লাখ` };
      break;
    }
    case "breadth_20":
      p = { en: `${Math.round(v * 100)}% of stocks above their 20-day average`, bn: `${Math.round(v * 100)}% শেয়ার ২০ দিনের গড়ের ওপরে` };
      break;
    case "mkt_ret_10":
      p = { en: `Market ${pctStr(ex, 1, true)} over 10 days`, bn: `১০ দিনে বাজার ${pctStr(ex, 1, true)}` };
      break;
    default:
      p = { en: feature, bn: feature };
  }
  return { en: p.en, bn: toBn(p.bn) };
}
