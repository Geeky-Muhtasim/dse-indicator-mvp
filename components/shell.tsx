"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { L, LangSwitch, V, useLang } from "@/components/lang";
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

function Brand() {
  return (
    <Link href="/" className="brand">
      <span className="mark gd" aria-hidden="true" />
      <span><b><L en="DSE Signal" bn="ডিএসই সংকেত" stack subClass="brand-sub" /></b><small>Explainable equity ranking</small></span>
    </Link>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { lang, setLang } = useLang();
  const { data: health, error } = useApi<Health>("/health");
  const [open, setOpen] = useState(false);

  // Close the mobile drawer on navigation and with Escape; lock page scroll while it is open.
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  const status = error ? "#F59AB8" : health ? "#7FD1A6" : "#9DB5A8";

  return (
    <div className="shell">
      {/* Top bar: phones and tablets only */}
      <header className="topbar">
        <button type="button" className="iconbtn" aria-label="Open menu" aria-expanded={open} aria-controls="mainnav" onClick={() => setOpen(true)}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <Brand />
        <span className="dot" style={{ background: status, marginLeft: "auto" }} aria-label={error ? "API unreachable" : "API online"} />
        <button type="button" className="langpill" onClick={() => setLang(lang === "en" ? "bi" : "en")} aria-label="Switch language">
          {lang === "en" ? "বাংলা" : "EN"}
        </button>
      </header>

      {open && <button type="button" className="scrim" aria-label="Close menu" onClick={() => setOpen(false)} />}

      <nav id="mainnav" className={`nav${open ? " open" : ""}`} aria-label="Main">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <Brand />
          <button type="button" className="iconbtn drawer-only" aria-label="Close menu" onClick={() => setOpen(false)}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
        </div>
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
            <span className="dot" style={{ background: status }} />
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
