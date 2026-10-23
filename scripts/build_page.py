"""Inline data/laws.json into the page templates.

Writes:
  index.html          artifact body for the claude.ai Lawbook (no document skeleton; not committed)
  docs/index.html     the Lawbook website (GitHub Pages from this repo's docs/)
  pocket/index.html   Pocket Lawbook, the phone-first edition (copied to danielgolliher/pocket-lawbook by publish.py)
Usage: python3 -I scripts/build_page.py
"""
import json
import re
from pathlib import Path

LAWBOOK = {
    "url": "https://danielgolliher.github.io/lawbook/",
    "title": "119th Congress Lawbook",
    "description": ("Explore every public law of the 119th Congress: what each one does, who sponsored it, "
                    "how the floor votes split and how long it took to become law."),
}
POCKET = {
    "url": "https://danielgolliher.github.io/pocket-lawbook/",
    "title": "Pocket Lawbook \U0001F1FA\U0001F1F8",
    "description": ("Every federal law signed since January 2025, one card each. Tap a card for the votes, "
                    "the sponsor, the timeline and what it does."),
}

root = Path(__file__).resolve().parent.parent
data = json.loads((root / "data" / "laws.json").read_text(encoding="utf-8"))
blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
meta_path = root / "data" / "meta.json"
as_of = json.loads(meta_path.read_text())["asOf"] if meta_path.exists() else None


def fill(template):
    out = template.replace("/*__LAWS__*/", blob)
    assert "/*__LAWS__*/" not in out
    # "Data current as of" comes from the last refresh (scripts/refresh.py writes data/meta.json).
    if as_of:
        out, n = re.subn(r'const TODAY = "\d{4}-\d{2}-\d{2}";', f'const TODAY = "{as_of}";', out)
        assert n == 1
    return out


def social(site, icons):
    return f"""<meta name="description" content="{site['description']}">
<link rel="canonical" href="{site['url']}">
{icons}
<meta property="og:type" content="website">
<meta property="og:title" content="{site['title']}">
<meta property="og:description" content="{site['description']}">
<meta property="og:url" content="{site['url']}">
<meta property="og:image" content="{site['url']}og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{site['title']}">
<meta name="twitter:description" content="{site['description']}">
<meta name="twitter:image" content="{site['url']}og-image.png">
"""


# The Lawbook: artifact body plus the standalone site.
body = fill((root / "app.html").read_text(encoding="utf-8"))
(root / "index.html").write_text(body, encoding="utf-8")
cut = body.index("</style>") + len("</style>")  # the template opens with its <title>, font links and <style>
head_part, body_part = body[:cut], body[cut:]
meta = ('<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        + social(LAWBOOK, '<link rel="icon" href="favicon.svg" type="image/svg+xml">')
        + "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}"
          "body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n")
docs = root / "docs"
docs.mkdir(exist_ok=True)
(docs / "index.html").write_text(f'<!doctype html>\n<html lang="en">\n<head>\n{meta}{head_part}\n</head>\n<body>{body_part}\n</body>\n</html>\n', encoding="utf-8")
(docs / ".nojekyll").write_text("")

# Pocket Lawbook: a complete document already; fill in its data and social tags.
pocket = fill((root / "pocket.html").read_text(encoding="utf-8"))
icons = '<link rel="icon" href="favicon.svg" type="image/svg+xml">\n<link rel="apple-touch-icon" href="apple-touch-icon.png">'
pocket = pocket.replace("<!--__HEAD__-->", social(POCKET, icons), 1)
assert "<!--__HEAD__-->" not in pocket
out = root / "pocket"
out.mkdir(exist_ok=True)
(out / "index.html").write_text(pocket, encoding="utf-8")
(out / ".nojekyll").write_text("")
print(f"index.html {len(body)/1024:.0f} KB; docs/index.html and pocket/index.html written")
