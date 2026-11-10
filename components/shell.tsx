"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { L, LangSwitch, V } from "@/components/lang";
import { useApi } from "@/lib/api";
import { dateLabel } from "@/lib/i18n";

const LINKS = [
  { href: "/", en: "Today's signals", bn: "আজকের সংকেত" },
  { href: "/stock/ALLTEX", match: "/stock", en: "Stock analysis", bn: "শেয়ার বিশ্লেষণ" },
  { href: "/evidence", en: "Model evidence", bn: "মডেলের প্রমাণ" },
  { href: "/regime", en: "Market regime", bn: "বাজার পরিস্থিতি" },
  { href: "/method", en: "Method", bn: "পদ্ধতি" },
];

type Health = { status: string; asof: string; model: string };

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { data: health, error } = useApi<Health>("/health");
  return (
    <div className="shell">
      <nav className="nav" aria-label="Main">
        <Link href="/" className="brand">
          <span className="mark gd" aria-hidden="true" />
          <span><b><L en="DSE Signal" bn="ডিএসই সংকেত" stack subClass="brand-sub" /></b><small>Explainable equity ranking</small></span>
        </Link>
        <LangSwitch />
        <div className="navlinks">
          {LINKS.map((l) => {
            const active = l.match ? path.startsWith(l.match) : path === l.href;
            return (
              <Link key={l.href} href={l.href} aria-current={active ? "page" : undefined}>
                <L en={l.en} bn={l.bn} stack />
              </Link>
            );
          })}
        </div>
        <div className="navfoot">
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="dot" style={{ background: error ? "#F59AB8" : health ? "#7FD1A6" : "#9DB5A8" }} />
            <span>
              {error ? <L en="API unreachable" bn="এপিআই সংযোগ নেই" /> : health ? <L en="API online" bn="এপিআই সংযুক্ত" /> : <L en="Connecting" bn="সংযোগ হচ্ছে" />}
            </span>
          </span>
          {health && (
            <span style={{ color: "var(--green-sub)" }}>
              <L en="Data to" bn="তথ্য" /> <V p={dateLabel(health.asof)} /> · <span className="en">model {health.model}</span>
            </span>
          )}
          <span className="en" style={{ color: "var(--green-sub)", fontSize: 12 }}>Not investment advice</span>
        </div>
      </nav>
      <main className="main">{children}</main>
    </div>
  );
}
