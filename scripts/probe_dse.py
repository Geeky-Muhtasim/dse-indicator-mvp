"""Diagnose what DSE's day-end archive returns for different dates and range widths.
Prints a summary per probe and saves the raw HTML for inspection (uploaded as an artifact)."""
import re
import sys
import time
from pathlib import Path

import requests

OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
HOSTS = ["https://old.dsebd.org/", "https://www.dsebd.org/", "https://dsebd.org/"]
PROBES = [
    ("recent_week_all", "2026-11-01", "2026-11-10", "All Instrument"),
    ("2024_week_all", "2024-01-01", "2024-01-07", "All Instrument"),
    ("2024_month_all", "2024-01-01", "2024-01-31", "All Instrument"),
    ("2021_week_all", "2021-01-03", "2021-01-07", "All Instrument"),
    ("2021_week_GP", "2021-01-03", "2021-01-07", "GP"),
    ("2020_year_GP", "2020-01-01", "2020-12-31", "GP"),
]

for host in HOSTS:
    for name, a, b, inst in PROBES:
        url = host + "day_end_archive.php"
        t = time.time()
        try:
            r = requests.get(url, params={"startDate": a, "endDate": b, "inst": inst, "archive": "data"},
                             headers=UA, timeout=120)
            html = r.text
            tag = re.sub(r"\W+", "_", host.split("//")[1]) + name
            (OUT / f"{tag}.html").write_text(html, encoding="utf-8", errors="ignore")
            rows = html.count("<tr")
            dates = sorted(set(re.findall(r"20\d\d-\d\d-\d\d", html)))
            classes = sorted(set(re.findall(r'<table[^>]*class="([^"]*)"', html)))[:4]
            msg = re.findall(r"(?i)(maximum[^<]{0,80}|no data[^<]{0,60}|not found[^<]{0,60}|limit[^<]{0,60})", html)[:3]
            print(f"{host:24} {name:16} HTTP {r.status_code} {len(html):>8,} bytes {rows:>5} <tr> "
                  f"dates {dates[:1]}..{dates[-1:]} n={len(dates)} {time.time()-t:5.1f}s tables={classes} hints={msg}", flush=True)
        except Exception as e:
            print(f"{host:24} {name:16} ERROR {type(e).__name__}: {str(e)[:150]}", flush=True)
        time.sleep(2)
sys.exit(0)
