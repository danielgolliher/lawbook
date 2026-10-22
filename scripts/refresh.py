"""Pull newly signed laws and updated records, then rebuild the Lawbook.

Usage:
  python3 -I scripts/refresh.py            # download, rebuild, print a report
  python3 -I scripts/refresh.py --offline  # rebuild from files already in raw/ (after editing build_data.py)

Set CONGRESS_API_KEY to use your own api.data.gov key; DEMO_KEY works for the one list call a run makes.
The last line printed is a JSON report. Exit status 1 means nothing was rebuilt.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (119th Congress Lawbook refresh)"}


def fail(msg):
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(1)


def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_to(url, path):
    try:
        data = get(url)
    except Exception as e:  # noqa: BLE001 - report every failure the same way
        return url, str(e)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return url, None


def run(*args):
    r = subprocess.run([sys.executable, "-I", *map(str, args)], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        fail(f"{Path(args[0]).name} failed: {r.stderr.strip()[-600:]}")
    return r


def law_list():
    key = os.environ.get("CONGRESS_API_KEY", "DEMO_KEY")
    bills, offset = [], 0
    while True:
        url = f"https://api.congress.gov/v3/law/119?api_key={key}&limit=250&offset={offset}&format=json"
        try:
            page = json.loads(get(url))
        except Exception as e:  # noqa: BLE001
            fail(f"Congress.gov API request failed: {e}")
        bills += page.get("bills", [])
        if not page.get("pagination", {}).get("next"):
            return bills
        offset += 250


def main():
    offline = "--offline" in sys.argv
    before = json.loads((DATA / "laws.json").read_text()) if (DATA / "laws.json").exists() else []
    before_ids = {(r["pvt"], r["id"]) for r in before}
    before_by = {(r["pvt"], r["id"]): r for r in before}
    errors = []

    if not offline:
        bills = law_list()
        known_public = sum(1 for r in before if not r["pvt"])
        api_public = sum(1 for b in bills for l in b["laws"] if l["type"] == "Public Law")
        if api_public < known_public:
            fail(f"API lists {api_public} public laws but the Lawbook already has {known_public}; refusing to shrink.")
        (RAW / "api_law.json").write_text(json.dumps({"bills": bills}, indent=1))

        # Bill status files change as summaries and actions are added, so refetch all of them.
        (RAW / "billstatus").mkdir(parents=True, exist_ok=True)
        jobs = []
        for b in bills:
            t, n = b["type"].lower(), b["number"]
            jobs.append((f"https://www.govinfo.gov/bulkdata/BILLSTATUS/119/{t}/BILLSTATUS-119{t}{n}.xml",
                         RAW / "billstatus" / f"BILLSTATUS-119{t}{n}.xml"))
        with ThreadPoolExecutor(8) as pool:
            errors += [f"{u}: {e}" for u, e in pool.map(lambda j: fetch_to(*j), jobs) if e]

    run("scripts/extract.py", RAW / "api_law.json", RAW / "billstatus", DATA / "laws_base.json")

    if not offline:
        base = json.loads((DATA / "laws_base.json").read_text())
        jobs = []
        (RAW / "votes").mkdir(exist_ok=True)
        (RAW / "text").mkdir(exist_ok=True)
        for law in base:
            for f in law["floor"]:
                u = f["url"]
                if not u:
                    continue
                m = re.search(r"/evs/(\d+)/roll(\d+)\.xml", u)
                if m:
                    name = f"house_{m.group(1)}_{m.group(2)}.xml"
                else:
                    name = "senate_" + Path(u).name
                if not (RAW / "votes" / name).exists():
                    jobs.append((u, RAW / "votes" / name))
            t = law["textUrls"]
            for kind in ("Public Law", "Private Law", "Enrolled Bill"):
                urls = [u for u in t.get(kind, []) if "/uslm/" in u] or [u for u in t.get(kind, []) if u.endswith(".xml")]
                if urls and not (RAW / "text" / Path(urls[0]).name).exists():
                    jobs.append((urls[0], RAW / "text" / Path(urls[0]).name))
        with ThreadPoolExecutor(6) as pool:
            errors += [f"{u}: {e}" for u, e in pool.map(lambda j: fetch_to(*j), jobs) if e]
        (DATA / "meta.json").write_text(json.dumps({"asOf": date.today().isoformat()}))

    run("scripts/enrich.py", DATA / "laws_base.json", RAW / "votes", RAW / "text", DATA / "laws_enriched.json")
    run("scripts/build_data.py", DATA / "laws_enriched.json", DATA / "laws.json")
    run("scripts/build_page.py")

    after = json.loads((DATA / "laws.json").read_text())
    pub = [r for r in after if not r["pvt"]]
    if len(pub) < sum(1 for r in before if not r["pvt"]):
        fail("The rebuilt Lawbook has fewer public laws than before; restore data/ from git and investigate.")

    def brief(r):
        return {"id": r["id"], "private": r["pvt"], "bill": r["bill"], "signed": r["signed"], "title": r["title"],
                "gist": r["gist"], "area": r["area"], "kind": r["kind"]}

    new = [brief(r) for r in after if (r["pvt"], r["id"]) not in before_ids]
    changed = []
    for r in after:
        old = before_by.get((r["pvt"], r["id"]))
        if not old:
            continue
        what = [k for k, label in (("summary", "summary"), ("stat", "Stat. citation"), ("words", "text"))
                if (old.get(k) is None) != (r.get(k) is None) or (k == "summary" and old.get(k) != r.get(k))]
        if what:
            changed.append({"id": r["id"], "updated": what})
    newest = max(pub, key=lambda r: r["n"])
    report = {
        "ok": True,
        "asOf": json.loads((DATA / "meta.json").read_text())["asOf"] if (DATA / "meta.json").exists() else None,
        "publicLaws": len(pub),
        "privateLaws": len(after) - len(pub),
        "newest": f"{newest['id']} ({newest['signed']})",
        "newLaws": new,
        "updated": changed,
        "unreviewed": [r["id"] for r in pub if r.get("unreviewed")],
        "needsLabel": [{"id": r["id"], "title": r["title"]} for r in pub if r.get("needsLabel")],
        "pendingSummary": [r["id"] for r in pub if r.get("gistPending")],
        "pendingText": [r["id"] for r in pub if r.get("words") is None],
        "downloadErrors": errors[:20],
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
