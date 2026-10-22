"""Merge enriched records with the explorer's editorial layer and write the app's data file.

Usage: python3 -I scripts/build_data.py data/laws_enriched.json data/laws.json
"""
import json
import re
import sys
from pathlib import Path

src, out = map(Path, sys.argv[1:3])

# Law type: an editorial grouping for this explorer, assigned from each CRS summary.
KIND = {}
for n in (2, 3, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 19, 20, 47, 48, 49, 50, 51, 52, 78, 85):
    KIND[n] = "rule"
for n in (4, 21, 28, 37, 74, 75, 86, 98, 103):
    KIND[n] = "money"
for n in (30, 35, 46, 53, 59, 79, 80, 81, 94, 104, 107, 117):
    KIND[n] = "honor"
for n in (23, 24, 25, 61, 63, 68, 91, 93, 105, 113, 114, 115, 122, 126, 128, 130, 132, 133):
    KIND[n] = "land"

# Short headlines for laws whose only title is the long official one.
LABEL = {
    2: "Overturns EPA's methane waste-emissions charge rule",
    3: "Overturns BOEM's offshore archaeological-report rule",
    5: "Overturns IRS broker reporting for DeFi transactions",
    6: "Overturns DOE standards for gas tankless water heaters",
    7: "Overturns DOE standards for walk-in coolers and freezers",
    8: "Overturns DOE appliance certification and labeling rule",
    9: "Overturns DOE standards for commercial refrigerators",
    10: "Overturns the CFPB's overdraft-fee rule",
    11: "Overturns CFPB oversight of digital payment apps",
    13: "Overturns NPS vehicle limits in Glen Canyon",
    14: "Overturns EPA air-toxics rule for tire manufacturing",
    15: "Revokes California's Advanced Clean Trucks waiver",
    16: "Revokes California's Advanced Clean Cars II waiver",
    17: "Revokes California's Omnibus Low-NOx waiver",
    19: "Overturns the OCC's bank-merger review rule",
    20: "Overturns EPA rule on reclassifying major pollution sources",
    35: "Names the Toms River, N.J., VA clinic for Leonard G. “Bud” Lomell",
    46: "Allows America 250 displays on the National Mall",
    47: "Overturns BLM's National Petroleum Reserve plan",
    48: "Overturns BLM's Miles City, Mont., coal-leasing plan",
    49: "Overturns BLM's North Dakota resource plan",
    50: "Overturns BLM's Central Yukon resource plan",
    51: "Overturns BLM's Buffalo, Wyo., coal plan",
    52: "Overturns BLM's ANWR coastal plain leasing plan",
    59: "Names the Guthrie, Okla., post office for Oscar J. Upham",
    78: "Overturns D.C.'s 2025 tax conformity act",
    80: "Clears the posthumous promotion of Army Capt. Cody Khork",
    81: "Medal of Honor for John W. Ripley",
    84: "Extends FISA Title VII authorities to April 30, 2026",
    85: "Overturns a mineral-leasing withdrawal in northeast Minnesota",
    87: "Extends FISA Title VII authorities to June 12, 2026",
    90: "Extends construction deadlines for some hydropower projects",
    95: "Lets Capitol Police officers serve to age 62",
    105: "Lifts deed restrictions on a Paducah, Ky., parcel",
    113: "Reauthorizes the Fort Peck Reservation rural water system",
    114: "Lets the Miami Tribe of Oklahoma pursue an Illinois land claim",
    115: "Adds the George C. Marshall House to the National Park System",
    117: "Names the Casper, Wyo., trails center for Barbara L. Cubin",
    126: "Conveys a Forest Service site to Gila County, Ariz.",
}

GIST = {
    44: "This act reauthorizes and revises federal programs for preventing and treating substance use disorders, "
        "including opioid prevention, treatment and recovery programs first set up by the 2018 SUPPORT Act.",
    84: "This act extends the authorities in title VII of the Foreign Intelligence Surveillance Act through "
        "April 30, 2026. No CRS summary has been published yet; this line restates the law's official title.",
}

ABBREV = r"(?:U\.S|e\.g|i\.e|Sec|No|Nos|Mr|Mrs|Ms|Dr|St|Jr|Sr|Inc|Co|Corp|Ft|Mt|vs|etc|Pub|L|Stat|D\.C|U\.S\.C|a\.m|p\.m)"


def first_sentence(text):
    for m in re.finditer(r"\.(?=\s+[A-Z(])", text):
        before = text[: m.start()]
        if re.search(ABBREV + r"$", before):
            continue
        if re.search(r"\b[A-Z]$", before):  # initials like "John W."
            continue
        return text[: m.end()]
    return text


def gist_for(law):
    if law["n"] in GIST and law["lawType"] == "Public Law":
        return GIST[law["n"]]
    blocks = law["summary"]["blocks"] if law["summary"] else []
    for b in blocks:
        if re.match(r"This (act|bill|joint resolution|resolution)\b", b):
            return first_sentence(b)
    for b in blocks:
        i = b.find("This act")
        if i >= 0:
            return first_sentence(b[i:])
    return None


def headline(law):
    if law["lawType"] == "Public Law" and law["n"] in LABEL:
        return LABEL[law["n"]], True
    if law["popularTitles"]:
        return law["popularTitles"][0], False
    return law["title"], False


laws = json.loads(src.read_text())
rows = []
for law in laws:
    head, is_label = headline(law)
    private = law["lawType"] != "Public Law"
    kind = "honor" if private else KIND.get(law["n"], "policy")
    s = law["summary"]
    rows.append({
        "id": law["id"],
        "pvt": private,
        "n": law["n"],
        "bill": law["bill"],
        "head": head,
        "isLabel": is_label,
        "title": law["title"],
        "official": law["length"]["longTitle"] or law["officialTitle"],
        "popular": law["popularTitles"],
        "short": law["shortTitles"],
        "kind": kind,
        "area": law["policyArea"],
        "subjects": law["subjects"],
        "gist": gist_for(law),
        "summary": {"v": s["version"], "d": s["date"], "b": s["blocks"]} if s else None,
        "intro": law["introduced"],
        "presented": law["presented"],
        "signed": law["signed"],
        "days": law["days"],
        "origin": law["originChamber"],
        "sponsor": law["sponsor"],
        "cos": law["cosponsors"],
        "committees": law["committees"],
        "floor": [{k: f.get(k) for k in ("chamber", "date", "stage", "method", "yea", "nay", "roll", "text",
                                          "url", "byParty", "tieBreaker", "majority")} for f in law["floor"]],
        "steps": law["milestones"],
        "words": law["length"]["words"],
        "stat": law["length"]["stat"],
        "statPages": law["length"]["statPages"],
        "textSource": law["textSource"],
        "pdf": law["pdfUrl"],
        "url": law["congressUrl"],
        "cbo": law["cbo"],
        "reports": law["reports"],
    })

missing_gist = [r["id"] for r in rows if not r["gist"]]
assert not missing_gist, missing_gist
out.write_text(json.dumps(rows, separators=(",", ":"), ensure_ascii=False))
print(f"wrote {len(rows)} rows, {out.stat().st_size/1024:.0f} KB")
