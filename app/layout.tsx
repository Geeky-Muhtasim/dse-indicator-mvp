import type { Metadata } from "next";
// Self-hosted variable fonts (weight and width axes), so the app never depends on a font CDN.
import "@fontsource-variable/anek-bangla/standard.css";
import "@fontsource-variable/anek-latin/standard.css";
import "./globals.css";
import { LangProvider } from "@/components/lang";
import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "DSE Signal",
  description: "Explainable Buy / Hold / Avoid signals for Dhaka Stock Exchange equities, updated after every session.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <LangProvider>
          <Shell>{children}</Shell>
        </LangProvider>
      </body>
    </html>
  );
}
