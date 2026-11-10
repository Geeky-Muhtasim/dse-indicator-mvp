"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Lang, Pair } from "@/lib/i18n";

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "en", setLang: () => {} });
const KEY = "dse-lang";

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => {
    try {
      const v = localStorage.getItem(KEY);
      if (v === "bi" || v === "en") setLangState(v);
    } catch {}
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang === "bi" ? "bn" : "en";
  }, [lang]);
  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(KEY, l);
    } catch {}
  };
  return <Ctx.Provider value={{ lang, setLang }}>{children}</Ctx.Provider>;
}

export const useLang = () => useContext(Ctx);

/** A label. English mode: English only. Bilingual: Bangla leads, English follows (stacked or inline). */
export function L({ p, en, bn, stack = false, subClass = "sub" }: { p?: Pair; en?: string; bn?: string; stack?: boolean; subClass?: string }) {
  const { lang } = useLang();
  const e = p?.en ?? en ?? "";
  const b = p?.bn ?? bn ?? e;
  if (lang === "en") return <>{e}</>;
  return stack ? (
    <>
      <span className="bn">{b}</span>
      <span className={subClass}>{e}</span>
    </>
  ) : (
    <>
      <span className="bn">{b}</span> <span className="en-inline">{e}</span>
    </>
  );
}

/** A value with no paired English (numbers, dates): picks one language. */
export function V({ p }: { p: Pair }) {
  const { lang } = useLang();
  return <>{lang === "bi" ? p.bn : p.en}</>;
}

export function LangSwitch() {
  const { lang, setLang } = useLang();
  return (
    <div className="seg seg-dark" role="group" aria-label="Language">
      <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>English</button>
      <button type="button" aria-pressed={lang === "bi"} onClick={() => setLang("bi")}>বাংলা + EN</button>
    </div>
  );
}
