"""Inline data/laws.json into app.html.

Writes index.html (artifact body, no document skeleton) and docs/index.html (the standalone
GitHub Pages site, with its own head and social tags).
Usage: python3 -I scripts/build_page.py
"""
import json
from pathlib import Path

SITE_URL = "https://danielgolliher.github.io/lawbook/"
TITLE = "119th Congress Lawbook"
DESCRIPTION = ("Explore every public law of the 119th Congress: what each one does, who sponsored it, "
               "how the floor votes split and how long it took to become law.")

root = Path(__file__).resolve().parent.parent
template = (root / "app.html").read_text(encoding="utf-8")
data = json.loads((root / "data" / "laws.json").read_text(encoding="utf-8"))
blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
body = template.replace("/*__LAWS__*/", blob)
assert "/*__LAWS__*/" not in body
(root / "index.html").write_text(body, encoding="utf-8")

# The template opens with its <title>, font links and <style>; those belong in <head> on the web.
cut = body.index("</style>") + len("</style>")
head_part, body_part = body[:cut], body[cut:]
meta = f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{DESCRIPTION}">
<link rel="canonical" href="{SITE_URL}">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<meta property="og:type" content="website">
<meta property="og:title" content="{TITLE}">
<meta property="og:description" content="{DESCRIPTION}">
<meta property="og:url" content="{SITE_URL}">
<meta property="og:image" content="{SITE_URL}og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{TITLE}">
<meta name="twitter:description" content="{DESCRIPTION}">
<meta name="twitter:image" content="{SITE_URL}og-image.png">
<style>:root{{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
"""
standalone = f'<!doctype html>\n<html lang="en">\n<head>\n{meta}{head_part}\n</head>\n<body>{body_part}\n</body>\n</html>\n'
docs = root / "docs"
docs.mkdir(exist_ok=True)
(docs / "index.html").write_text(standalone, encoding="utf-8")
(docs / ".nojekyll").write_text("")
print(f"index.html {len(body)/1024:.0f} KB; docs/index.html {len(standalone)/1024:.0f} KB")
