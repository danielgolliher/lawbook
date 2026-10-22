"""Add party splits for roll-call votes and length/citation from the enacted text.

Usage: python3 -I scripts/enrich.py data/laws_base.json raw/votes raw/text data/laws_enriched.json
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

base_path, votes_dir, text_dir, out_path = map(Path, sys.argv[1:5])
laws = json.loads(base_path.read_text())

PARTY = {"Republican": "R", "Democratic": "D", "Independent": "I"}


def house_vote(path):
    root = ET.parse(path).getroot()
    out = {}
    for p in root.iter("totals-by-party"):
        k = PARTY.get(p.findtext("party").strip(), "I")
        out[k] = {"yea": int(p.findtext("yea-total")), "nay": int(p.findtext("nay-total")),
                  "present": int(p.findtext("present-total")), "nv": int(p.findtext("not-voting-total"))}
    meta = root.find("vote-metadata")
    return {"byParty": out, "question": meta.findtext("vote-question"), "result": meta.findtext("vote-result"),
            "type": meta.findtext("vote-type")}


def senate_vote(path):
    root = ET.parse(path).getroot()
    out = {k: {"yea": 0, "nay": 0, "present": 0, "nv": 0} for k in "RDI"}
    for m in root.iter("member"):
        p = m.findtext("party")
        cast = m.findtext("vote_cast")
        key = {"Yea": "yea", "Nay": "nay", "Present": "present"}.get(cast, "nv")
        out[p if p in out else "I"][key] += 1
    tie = root.findtext("tie_breaker/by_whom")
    return {"byParty": out, "question": root.findtext("question"), "result": root.findtext("vote_result"),
            "majority": root.findtext("majority_requirement"),
            "tieBreaker": tie.strip() if tie and tie.strip() else None}


def vote_file(url):
    m = re.search(r"/evs/(\d+)/roll(\d+)\.xml", url)
    if m:
        return votes_dir / f"house_{m.group(1)}_{m.group(2)}.xml", house_vote
    m = re.search(r"/(vote_119_\d_\d+)\.xml", url)
    return votes_dir / f"senate_{m.group(1)}.xml", senate_vote


def text_stats(path):
    """Word count of the operative text; Stat. citation and page span for slip laws."""
    raw = path.read_text(encoding="utf-8")
    root = ET.fromstring(raw.encode("utf-8"))
    body = None
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in ("main", "legis-body", "resolution-body"):
            body = el
            break
    body = body if body is not None else root
    # Drop margin notes and page headers so they don't count as words.
    def count(text):
        return len(re.findall(r"[A-Za-z0-9][\w'’.,-]*", text)) if text else 0

    def walk(el):
        n = 0
        if el.tag.split("}")[-1] not in ("page", "sidenote", "notes", "note"):
            n += count(el.text) + sum(walk(child) for child in el)
        return n + count(el.tail)

    words = walk(body) - count(body.tail)
    long_title = None
    for el in root.iter():
        if el.tag.split("}")[-1] in ("officialTitle", "official-title"):
            parts = [el.text or ""]
            for child in el:
                if child.tag.split("}")[-1] != "sidenote":
                    parts.append("".join(child.itertext()))
                parts.append(child.tail or "")
            long_title = re.sub(r"\s+", " ", "".join(parts)).strip()
            break
    stat = re.findall(r"<citableAs>(\d+ Stat\. \d+)</citableAs>", raw)
    pages = sorted({int(p) for p in re.findall(r'identifier="/us/stat/\d+/(\d+)"', raw)})
    return {"words": words, "stat": stat[0] if stat else None, "longTitle": long_title,
            "statPages": (pages[-1] - pages[0] + 1) if pages else None}


for law in laws:
    for f in law["floor"]:
        if f["url"]:
            path, fn = vote_file(f["url"])
            if path.exists():
                f.update(fn(path))
    t = law["textUrls"]
    pl = [u for u in t.get("Public Law", []) + t.get("Private Law", []) if "/uslm/" in u]
    enr = [u for u in t.get("Enrolled Bill", []) if "/uslm/" in u] or [u for u in t.get("Enrolled Bill", []) if u.endswith(".xml")]
    pl = [u for u in pl if (text_dir / Path(u).name).exists()]
    enr = [u for u in enr if (text_dir / Path(u).name).exists()]
    if not (pl or enr):
        # Brand-new laws can appear before GovInfo posts any text.
        law["length"] = {"words": None, "stat": None, "longTitle": None, "statPages": None}
        law["textSource"] = None
        law["pdfUrl"] = None
        continue
    src = pl[0] if pl else enr[0]
    stats = text_stats(text_dir / Path(src).name)
    if pl and enr:
        # Word counts from the slip law include its margin apparatus; the enrolled bill is the cleaner count.
        stats["words"] = text_stats(text_dir / Path(enr[0]).name)["words"]
    law["length"] = stats
    law["textSource"] = "Public Law" if pl else "Enrolled Bill"
    pkg = Path(src).stem
    law["pdfUrl"] = f"https://www.govinfo.gov/content/pkg/{pkg}/pdf/{pkg}.pdf"

out_path.write_text(json.dumps(laws, indent=1))
print("wrote", out_path)
