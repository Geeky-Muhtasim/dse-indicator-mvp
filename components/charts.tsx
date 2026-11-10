"use client";
import { useEffect, useRef, useState } from "react";

type Series = { name: string; color: string; dash?: string; values: (number | null)[] };

/** Multi-line chart on one y-axis, with a crosshair tooltip. Lines are 2px; the hit area is the full plot. */
export function LineChart({
  labels, series, height = 220, yFmt = (v: number) => v.toFixed(2), refLine, refLabel, shade, ariaLabel, fill = false,
}: {
  labels: string[]; series: Series[]; height?: number; yFmt?: (v: number) => string;
  refLine?: number; refLabel?: string; shade?: boolean[]; ariaLabel: string;
  /** Grow to fill the parent's height (parent must be a flex column); `height` becomes the minimum. */
  fill?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(760);
  const [boxH, setBoxH] = useState(height);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      setW(Math.max(280, Math.round(e.contentRect.width)));
      setBoxH(Math.round(e.contentRect.height));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = fill ? Math.max(height, boxH) : height;
  const pad = { l: 48, r: 12, t: 12, b: 26 };
  const all = series.flatMap((s) => s.values.filter((v): v is number => v != null));
  if (refLine != null) all.push(refLine);
  let lo = Math.min(...all), hi = Math.max(...all);
  // Round axis ends to a 1/2/2.5/5 step so tick labels read cleanly.
  const raw = (hi - lo || Math.abs(hi) || 1) / 3;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= raw) ?? raw;
  lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
  if (hi === lo) hi = lo + step;
  const n = labels.length;
  const x = (i: number) => pad.l + (n <= 1 ? 0 : (i * (W - pad.l - pad.r)) / (n - 1));
  const y = (v: number) => pad.t + ((hi - v) * (H - pad.t - pad.b)) / (hi - lo);
  const ticks: number[] = [];
  for (let t = lo; t <= hi + step / 2; t += step) ticks.push(Math.round(t / step) * step);
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  const onMove = (e: React.MouseEvent) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  };
  const xi = [0, Math.floor((n - 1) / 3), Math.floor((2 * (n - 1)) / 3), n - 1];

  return (
    <div ref={box} style={fill ? { position: "relative", flex: "1 1 auto", minHeight: height } : { position: "relative" }}>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={ariaLabel}
        style={fill ? { position: "absolute", inset: 0, width: "100%", height: "100%", display: "block" } : { width: "100%", height: H, display: "block" }}
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {shade && shade.map((s, i) => s && i < n - 1 ? (
          <rect key={`s${i}`} x={x(i)} y={pad.t} width={x(i + 1) - x(i)} height={H - pad.t - pad.b} fill="#FBEFF3" />
        ) : null)}
        {ticks.map((t, k) => (
          <g key={k}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="#DFE6E0" />
            <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="#4A6458">{yFmt(t)}</text>
          </g>
        ))}
        {refLine != null && (
          <g>
            <line x1={pad.l} x2={W - pad.r} y1={y(refLine)} y2={y(refLine)} stroke="#B3124E" strokeDasharray="5 4" />
            {refLabel && <text x={W - pad.r} y={y(refLine) - 6} textAnchor="end" fontSize="11" fill="#8E0E3D">{refLabel}</text>}
          </g>
        )}
        <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="#0F2A22" />
        {xi.map((i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"} fontSize="11" fill="#4A6458">{labels[i]}</text>
        ))}
        {series.map((s) => {
          let d = "";
          s.values.forEach((v, i) => {
            if (v == null) return;
            d += `${d === "" || s.values[i - 1] == null ? "M" : "L"}${x(i).toFixed(1)} ${y(v).toFixed(1)} `;
          });
          return <path key={s.name} d={d} fill="none" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} strokeLinejoin="round" />;
        })}
        {hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={H - pad.b} stroke="#0F2A22" strokeOpacity="0.4" />
            {series.map((s) => s.values[hover] != null && (
              <circle key={s.name} cx={x(hover)} cy={y(s.values[hover]!)} r="4" fill={s.color} stroke="#F8FAF7" strokeWidth="2" />
            ))}
          </g>
        )}
      </svg>
      {hover != null && (
        <div className="tip" style={{ left: `${(x(hover) / W) * 100}%`, top: `${(pad.t / H) * 100}%` }}>
          <b>{labels[hover]}</b>
          {series.map((s) => s.values[hover] != null && (
            <div key={s.name}><span className="sw" style={{ background: s.color, width: 8, height: 8, marginRight: 6 }} />{s.name}: {yFmt(s.values[hover]!)}</div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Volume strip under a price chart. */
export function VolumeBars({ values }: { values: number[] }) {
  const mx = Math.max(...values, 1);
  return (
    <div className="bars" style={{ height: 44, marginLeft: 48, marginRight: 12, gap: 2 }} aria-hidden="true">
      {values.map((v, i) => <span key={i} style={{ height: `${Math.max(2, (v / mx) * 100)}%`, background: "#C3C7E8" }} />)}
    </div>
  );
}

/** Bars around a zero line: positive up in `pos`, negative down in `neg`. The zero line sits
 *  where the data puts it, so a series with no negatives uses the full height. */
export function ZeroBars({ values, labels, fmt, height = 220, pos = "#262B6B", neg = "#B3124E", meanLine }: {
  values: number[]; labels?: string[]; fmt: (v: number) => string; height?: number; pos?: string; neg?: string; meanLine?: number;
}) {
  const up = Math.max(0, ...values), dn = Math.max(0, ...values.map((v) => -v));
  const topH = Math.round((height * up) / (up + dn || 1));
  return (
    <div style={{ height, display: "flex", flexDirection: "column" }}>
      <div className="bars" style={{ height: topH, borderBottom: "1px solid #0F2A22", position: "relative" }}>
        {meanLine != null && meanLine > 0 && up > 0 && <span style={{ position: "absolute", left: 0, right: 0, bottom: `${(meanLine / up) * 100}%`, borderTop: "1px dashed #0F2A22", zIndex: 1 }} />}
        {values.map((v, i) => <span key={i} title={`${labels?.[i] ?? ""} ${fmt(v)}`} style={{ height: v > 0 ? `${(v / up) * 100}%` : 0, background: pos }} />)}
      </div>
      <div className="bars" style={{ height: height - topH, alignItems: "flex-start" }}>
        {values.map((v, i) => <span key={i} title={`${labels?.[i] ?? ""} ${fmt(v)}`} style={{ height: v < 0 ? `${(-v / dn) * 100}%` : 0, background: neg }} />)}
      </div>
    </div>
  );
}
