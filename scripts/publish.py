"""Publish a rebuilt Lawbook: push the GitHub Pages repo, then copy the page into the
data.maximumnewyork.com repo and push that too (its GitHub Action deploys on push).

Usage: python3 -I scripts/publish.py "<one-line summary for the commit message>"
Prints one JSON line. It never pushes commits it did not make: if either repo has unpushed
commits or its pull is not a fast-forward, that repo is skipped and the reason reported.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIRROR = Path.home() / "Downloads" / "nyc-budget-graphics"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
TRAILER = "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
FRAME_SCRIPT = """<script>
/* Inside the Data Viz & Art site this page runs in an iframe: send outside links to a new tab. */
if (window.top !== window) document.querySelectorAll('a[href^="http"]').forEach(function (a) { a.target = '_blank'; a.rel = 'noopener'; });
</script>
</body>"""


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def ready(repo):
    """Up to date with origin/main and nothing unpushed, or the reason it is not."""
    if git(repo, "rev-parse", "--abbrev-ref", "HEAD") != "main":
        return "not on main"
    git(repo, "fetch", "-q", "origin", "main")
    if git(repo, "rev-list", "--count", "origin/main..HEAD") != "0":
        return "has local commits that are not pushed"
    r = subprocess.run(["git", "-C", str(repo), "merge", "--ff-only", "-q", "origin/main"], capture_output=True, text=True)
    if r.returncode:
        return "could not fast-forward to origin/main: " + (r.stderr.strip() or r.stdout.strip())
    return None


def og_image():
    """Re-render the social preview (dark theme) so its counts match the data."""
    if not CHROME.exists():
        return "Chrome not found; kept the old preview image"
    tmp = ROOT / "docs" / "_og.html"
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    html = html.replace('<html lang="en">', '<html lang="en" data-theme="dark">', 1)
    html = html.replace("</head>", "<style>.main,.foot{display:none!important}.masthead{padding-block:26px 18px!important}</style></head>", 1)
    tmp.write_text(html, encoding="utf-8")
    try:
        subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1.2",
                        "--window-size=1000,525", "--virtual-time-budget=6000",
                        f"--screenshot={ROOT / 'docs' / 'og-image.png'}", tmp.as_uri()],
                       capture_output=True, timeout=90, check=True)
    except Exception as e:  # noqa: BLE001
        return f"preview image not updated: {e}"
    finally:
        tmp.unlink(missing_ok=True)
    return None


def main():
    summary = sys.argv[1] if len(sys.argv) > 1 else "Weekly refresh"
    out = {"lawbook": None, "mirror": None, "notes": []}

    # Sanity check: the built page carries the same laws as data/laws.json.
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    blob = re.search(r'<script type="application/json" id="laws-data">(.*?)</script>', page, re.S).group(1)
    rows = json.loads(blob.replace("<\\/", "</"))
    data = json.loads((ROOT / "data" / "laws.json").read_text())
    if len(rows) != len(data) or len(rows) < 100:
        print(json.dumps({"ok": False, "error": f"docs/index.html has {len(rows)} laws, data has {len(data)}"}))
        sys.exit(1)

    note = og_image()
    if note:
        out["notes"].append(note)

    # 1. The lawbook repo (GitHub Pages).
    why = ready(ROOT)
    if why:
        out["lawbook"] = f"skipped: {why}"
    else:
        git(ROOT, "add", "-A")
        if subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"]).returncode:
            git(ROOT, "commit", "-q", "-m", summary + TRAILER)
            git(ROOT, "push", "-q", "origin", "main")
            out["lawbook"] = "pushed " + git(ROOT, "rev-parse", "--short", "HEAD")
        else:
            out["lawbook"] = "no changes"

    # 2. The data.maximumnewyork.com mirror. Only its two Lawbook files are touched or committed.
    paths = ["public/lawbook/app.html", "public/og-lawbook.png"]
    why = ready(MIRROR) if MIRROR.exists() else "repo not found at " + str(MIRROR)
    if why:
        out["mirror"] = f"skipped: {why}"
    else:
        page_html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        assert page_html.count("</body>") == 1
        (MIRROR / paths[0]).write_text(page_html.replace("</body>", FRAME_SCRIPT), encoding="utf-8")
        shutil.copyfile(ROOT / "docs" / "og-image.png", MIRROR / paths[1])
        git(MIRROR, "add", "--", *paths)
        if subprocess.run(["git", "-C", str(MIRROR), "diff", "--cached", "--quiet", "--", *paths]).returncode:
            git(MIRROR, "commit", "-q", "-m", f"Lawbook: {summary[0].lower() + summary[1:]}" + TRAILER, "--", *paths)
            git(MIRROR, "push", "-q", "origin", "main")
            out["mirror"] = "pushed " + git(MIRROR, "rev-parse", "--short", "HEAD")
        else:
            out["mirror"] = "no changes"

    out["ok"] = not str(out["lawbook"]).startswith("skipped") and not str(out["mirror"]).startswith("skipped")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
