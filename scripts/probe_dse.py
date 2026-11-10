"""Diagnose DSE data sources from a CI runner: how far back the archive page has data,
and whether the JSON API accepts a browser User-Agent. Saves raw responses as an artifact."""
import re
import time
from pathlib import Path

from bdshare.util import vars as vs
from bdshare.util.helper import _session  # carries bdshare's CA bundle for old.dsebd.org

OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
           "Accept": "application/json, text/plain, */*", "Referer": "https://dse.com.bd/", "Origin": "https://dse.com.bd"}

print("== archive page, one week of all instruments per year ==", flush=True)
for y in [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2018]:
    a, b = f"{y}-03-01", f"{y}-03-10"
    if y == 2026:
        a, b = "2026-11-01", "2026-11-10"
    t = time.time()
    try:
        r = _session.get(vs.DSE_LEGACY_URL + vs.DSE_DEA_URL,
                         params={"startDate": a, "endDate": b, "inst": "All Instrument", "archive": "data"}, timeout=120)
        html = r.text
        (OUT / f"archive_{y}.html").write_text(html, encoding="utf-8", errors="ignore")
        dates = sorted(set(re.findall(r">\s*(20\d\d-\d\d-\d\d)\s*<", html)))
        print(f"archive {y}: HTTP {r.status_code} {len(html):>9,} B  <tr>={html.count('<tr'):>5}  "
              f"dates={dates[:1]}..{dates[-1:]} n={len(dates)}  {time.time()-t:.1f}s", flush=True)
    except Exception as e:
        print(f"archive {y}: ERROR {type(e).__name__}: {str(e)[:160]}", flush=True)
    time.sleep(2)

print("== archive page, single stock (GP) over a whole year ==", flush=True)
for y in [2024, 2021, 2020]:
    try:
        r = _session.get(vs.DSE_LEGACY_URL + vs.DSE_DEA_URL,
                         params={"startDate": f"{y}-01-01", "endDate": f"{y}-12-31", "inst": "GP", "archive": "data"}, timeout=120)
        dates = sorted(set(re.findall(r">\s*(20\d\d-\d\d-\d\d)\s*<", r.text)))
        print(f"GP {y}: HTTP {r.status_code} rows={len(dates)} {dates[:1]}..{dates[-1:]}", flush=True)
    except Exception as e:
        print(f"GP {y}: ERROR {type(e).__name__}: {str(e)[:160]}", flush=True)
    time.sleep(2)

print("== JSON API day-end ==", flush=True)
for label, headers in [("bdshare UA", {}), ("browser UA", BROWSER)]:
    for a, b in [("2026-11-09", "2026-11-10"), ("2021-03-01", "2021-03-02")]:
        try:
            r = _session.get(vs.DSE_URL + vs.DSE_API_DAY_END, params={"from": a, "to": b, "page": 1},
                             headers=headers, timeout=60)
            body = r.text
            (OUT / f"api_{label.split()[0]}_{a}.json").write_text(body[:200000], encoding="utf-8", errors="ignore")
            print(f"api {label:10} {a}: HTTP {r.status_code} {len(body):,} B  head={body[:160]!r}", flush=True)
        except Exception as e:
            print(f"api {label:10} {a}: ERROR {type(e).__name__}: {str(e)[:160]}", flush=True)
        time.sleep(2)
