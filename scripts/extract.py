"""Turn govinfo BILLSTATUS XML for every 119th Congress law into data/laws_base.json.

Usage: python3 -I scripts/extract.py raw/api_law.json raw/billstatus data/laws_base.json
"""
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

api_path, bs_dir, out_path = map(Path, sys.argv[1:4])

BILL_LABEL = {"HR": "H.R.", "S": "S.", "HJRES": "H.J.Res.", "SJRES": "S.J.Res."}
CONGRESS_SLUG = {"HR": "house-bill", "S": "senate-bill", "HJRES": "house-joint-resolution",
                 "SJRES": "senate-joint-resolution"}
HOUSE_PASS = {"8000", "19500"}
SENATE_PASS = {"17000", "20500"}


def txt(el, path, default=None):
    v = el.findtext(path)
    return v.strip() if v and v.strip() else default


def clean_summary(raw):
    """CRS summaries are escaped HTML. Keep paragraphs and list items as plain blocks."""
    if not raw:
        return []
    s = raw
    s = re.sub(r"</?(strong|em|b|i|u|span)[^>]*>", "", s)
    s = re.sub(r"<li[^>]*>", "\n• ", s)
    s = re.sub(r"</(p|li|ul|ol|h\d)>|<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    blocks = [re.sub(r"\s+", " ", b).strip() for b in s.split("\n")]
    return [b for b in blocks if b and b != "•"]


def vote_from_text(t):
    """Pull method and tally from a passage action's text."""
    tl = t.lower()
    m = re.search(r"(\d+)\s*-\s*(\d+)", t)
    roll = re.search(r"(?:Roll no\.|Record Vote Number:)\s*(\d+)", t)
    if "voice vote" in tl:
        method = "Voice vote"
    elif "unanimous consent" in tl or "without objection" in tl:
        method = "Unanimous consent"
    elif m:
        method = "Roll call"
    else:
        method = "Other"
    return {
        "method": method,
        "yea": int(m.group(1)) if m and method == "Roll call" else None,
        "nay": int(m.group(2)) if m and method == "Roll call" else None,
        "roll": int(roll.group(1)) if roll else None,
    }


api = json.loads(api_path.read_text())
laws = []
for entry in api["bills"]:
    btype, bnum = entry["type"], entry["number"]
    bs_path = bs_dir / f"BILLSTATUS-119{btype.lower()}{bnum}.xml"
    if not bs_path.exists():
        # GovInfo's bulk file can lag a day or two behind a signing; the law joins on a later run.
        print(f"skipping {btype} {bnum}: no bill status file yet", file=sys.stderr)
        continue
    root = ET.parse(bs_path).getroot()
    b = root.find("bill")
    # The API list is the authority on law numbers; the bill status file may not have caught up.
    law_type = entry["laws"][0]["type"]
    law_no = entry["laws"][0]["number"]

    # Titles
    titles = b.find("titles")
    display = txt(b, "title")
    official = None
    short_titles = []
    popular = []
    for it in titles.findall("item"):
        tt = txt(it, "titleType", "")
        if tt.startswith("Official Title as Introduced") and not official:
            official = txt(it, "title")
        if "Short Title" in tt and "portions" not in tt and txt(it, "billTextVersionCode") == "ENR":
            st = txt(it, "title")
            if st and st not in short_titles:
                short_titles.append(st)
        if tt == "Popular Titles":
            popular.append(txt(it, "title"))
    for it in titles.findall("item"):
        if txt(it, "titleType", "").startswith("Official Title as") and "Enrolled" in txt(it, "titleType", ""):
            official = txt(it, "title")

    # Sponsor + cosponsors
    sp = b.find("sponsors/item")
    sponsor = {
        "name": f"{txt(sp, 'firstName', '')} {txt(sp, 'lastName', '')}".strip(),
        "full": txt(sp, "fullName"),
        "party": txt(sp, "party"),
        "state": txt(sp, "state"),
        "district": txt(sp, "district"),
        "bioguide": txt(sp, "bioguideId"),
        "chamber": "Senate" if txt(sp, "fullName", "").startswith("Sen.") else "House",
    }
    cos = {"R": 0, "D": 0, "I": 0}
    cos_withdrawn = 0
    for it in b.findall("cosponsors/item"):
        if txt(it, "sponsorshipWithdrawnDate"):
            cos_withdrawn += 1
            continue
        p = txt(it, "party", "I")
        cos[p if p in cos else "I"] = cos.get(p if p in cos else "I", 0) + 1

    # Committees (top level only)
    committees = []
    for it in b.findall("committees/item"):
        name = txt(it, "name")
        ch = txt(it, "chamber")
        if name and (ch, name) not in [(c["chamber"], c["name"]) for c in committees]:
            committees.append({"chamber": ch, "name": name})

    # Actions
    actions = []
    for it in b.findall("actions/item"):
        actions.append({
            "date": txt(it, "actionDate"),
            "time": txt(it, "actionTime"),
            "text": txt(it, "text", ""),
            "type": txt(it, "type"),
            "code": txt(it, "actionCode"),
            "source": txt(it, "sourceSystem/name"),
            "votes": [{"roll": int(txt(v, "rollNumber")), "url": txt(v, "url"), "chamber": txt(v, "chamber"),
                       "date": txt(v, "date")} for v in it.findall("recordedVotes/recordedVote")],
        })
    actions.sort(key=lambda a: (a["date"], a["time"] or ""))

    def first(codes):
        for a in actions:
            if a["code"] in codes:
                return a
        return None

    introduced = txt(b, "introducedDate")
    became = first({"36000", "41000"})
    signed_date = became["date"] if became else entry["latestAction"]["actionDate"]
    presented = first({"28000"})

    floor = []
    seen = set()
    for a in actions:
        if a["code"] in HOUSE_PASS | SENATE_PASS and a["source"] == "Library of Congress":
            key = (a["date"], a["text"])
            if key in seen:
                continue
            seen.add(key)
            v = vote_from_text(a["text"])
            v.update({
                "chamber": "House" if a["code"] in HOUSE_PASS else "Senate",
                "date": a["date"],
                "stage": "Resolving differences" if a["code"] in {"19500", "20500"} else "Passage",
                "text": re.sub(r"^(Passed/agreed to in (House|Senate): |Resolving differences -- (House|Senate) actions: )",
                               "", a["text"]),
                "url": a["votes"][0]["url"] if a["votes"] else None,
            })
            floor.append(v)

    # Key milestones for the journey strip
    milestones = [{"label": "Introduced", "date": introduced}]
    for a in actions:
        if a["code"] in {"5000", "14000", "14500", "1010"} and a["source"] == "Library of Congress":
            milestones.append({"label": "Reported by committee", "date": a["date"]})
            break
    for f in floor:
        milestones.append({"label": f"{f['stage']} · {f['chamber']}", "date": f["date"]})
    if presented:
        milestones.append({"label": "Presented to the President", "date": presented["date"]})
    milestones.append({"label": "Signed into law", "date": signed_date})

    # Summary: latest CRS version
    summaries = sorted(b.findall("summaries/summary"), key=lambda s: (txt(s, "actionDate", ""), txt(s, "versionCode", "")))
    summary = None
    if summaries:
        s = summaries[-1]
        summary = {"version": txt(s, "actionDesc"), "date": txt(s, "actionDate"),
                   "blocks": clean_summary(txt(s, "text", ""))}

    # Text links
    text_urls = {}
    for it in b.findall("textVersions/item"):
        t = txt(it, "type")
        for fmt in it.findall("formats/item"):
            u = txt(fmt, "url")
            if u:
                text_urls.setdefault(t, []).append(u)

    subjects = [txt(it, "name") for it in b.findall("subjects/legislativeSubjects/item")]
    cbo = [{"title": txt(c, "title"), "url": txt(c, "url"), "date": txt(c, "pubDate")}
           for c in b.findall("cboCostEstimates/item")]
    reports = [txt(c, "citation") for c in b.findall("committeeReports/committeeReport")]

    d_intro = date.fromisoformat(introduced)
    d_signed = date.fromisoformat(signed_date)
    laws.append({
        "id": law_no,
        "lawType": law_type,
        "n": int(law_no.split("-")[1]),
        "billType": btype,
        "billNumber": int(bnum),
        "bill": f"{BILL_LABEL[btype]} {bnum}",
        "title": display,
        "shortTitles": short_titles,
        "popularTitles": popular,
        "officialTitle": official,
        "introduced": introduced,
        "presented": presented["date"] if presented else None,
        "signed": signed_date,
        "days": (d_signed - d_intro).days,
        "originChamber": txt(b, "originChamber"),
        "sponsor": sponsor,
        "cosponsors": cos,
        "cosponsorsWithdrawn": cos_withdrawn,
        "committees": committees,
        "policyArea": txt(b, "policyArea/name"),
        "subjects": subjects,
        "summary": summary,
        "floor": floor,
        "milestones": milestones,
        "actionCount": len({(a["date"], a["text"]) for a in actions}),
        "textUrls": text_urls,
        "cbo": cbo,
        "reports": reports,
        "congressUrl": f"https://www.congress.gov/bill/119th-congress/{CONGRESS_SLUG[btype]}/{bnum}",
    })

laws.sort(key=lambda x: (x["lawType"] != "Public Law", x["n"]))
out_path.write_text(json.dumps(laws, indent=1))
print(f"wrote {len(laws)} laws to {out_path}")
