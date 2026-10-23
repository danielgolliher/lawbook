"""Publish a rebuilt Lawbook to its three sites:
  1. this repo (danielgolliher/lawbook): GitHub Pages serves docs/
  2. danielgolliher/pocket-lawbook: the phone edition, copied from pocket/
  3. danielgolliher/nyc-budget-graphics: the data.maximumnewyork.com mirror (its GitHub Action deploys on push)

Usage: python3 -I scripts/publish.py "<one-line summary for the commit message>"
Prints one JSON line. It never pushes commits it did not make: if a repo has unpushed commits or
its pull is not a fast-forward, that repo is skipped and the reason reported. In the other two
repos only the files listed below are touched or committed.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = Path.home() / "Downloads"
POCKET_REPO = DOWNLOADS / "pocket-lawbook"
MIRROR_REPO = DOWNLOADS / "nyc-budget-graphics"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
TRAILER = "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
FRAME_SCRIPT = """<script>
/* Inside the Data Viz & Art site this page runs in an iframe: send outside links to a new tab. */
if (window.top !== window) document.querySelectorAll('a[href^="http"]').forEach(function (a) { a.target = '_blank'; a.rel = 'noopener'; });
</script>
</body>"""


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def ready(repo):
    """None when the repo is on main, has nothing unpushed and fast-forwards to origin; else why not."""
    if not (repo / ".git").exists():
        return f"repo not found at {repo}"
    if git(repo, "rev-parse", "--abbrev-ref", "HEAD") != "main":
        return "not on main"
    git(repo, "fetch", "-q", "origin", "main")
    if git(repo, "rev-list", "--count", "origin/main..HEAD") != "0":
        return "has local commits that are not pushed"
    r = subprocess.run(["git", "-C", str(repo), "merge", "--ff-only", "-q", "origin/main"], capture_output=True, text=True)
    if r.returncode:
        return "could not fast-forward to origin/main: " + (r.stderr.strip() or r.stdout.strip())
    return None


def staged(repo, paths=()):
    return subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet", "--", *paths]).returncode != 0


def og_image(page, out, extra_css, dark=False):
    """Re-render a social preview card (1200x630) from the built page so its counts stay current."""
    if not CHROME.exists():
        return f"Chrome not found; kept {out.name}"
    html = page.read_text(encoding="utf-8")
    if dark:
        html = html.replace('<html lang="en">', '<html lang="en" data-theme="dark">', 1)
    html = html.replace("</head>", f"<style>{extra_css}</style></head>", 1)
    tmp = page.with_name("_og.html")
    tmp.write_text(html, encoding="utf-8")
    try:
        subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1.2",
                        "--window-size=1000,525", "--virtual-time-budget=6000", f"--screenshot={out}", tmp.as_uri()],
                       capture_output=True, timeout=90, check=True)
    except Exception as e:  # noqa: BLE001
        return f"{out.name} not updated: {e}"
    finally:
        tmp.unlink(missing_ok=True)
    return None


def sync(repo, files, message):
    """Copy {repo path: bytes} into another repo, then commit and push only those paths."""
    why = ready(repo)
    if why:
        return f"skipped: {why}"
    for rel, content in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(content)
    paths = list(files)
    git(repo, "add", "--", *paths)
    if not staged(repo, paths):
        return "no changes"
    git(repo, "commit", "-q", "-m", message + TRAILER, "--", *paths)
    git(repo, "push", "-q", "origin", "main")
    return "pushed " + git(repo, "rev-parse", "--short", "HEAD")


def main():
    summary = sys.argv[1] if len(sys.argv) > 1 else "Weekly refresh"
    out = {"lawbook": None, "pocket": None, "mirror": None, "notes": []}

    # Sanity check: both built pages carry the same laws as data/laws.json.
    data = json.loads((ROOT / "data" / "laws.json").read_text())
    for page in (ROOT / "docs" / "index.html", ROOT / "pocket" / "index.html"):
        blob = re.search(r'<script type="application/json" id="laws-data">(.*?)</script>', page.read_text(encoding="utf-8"), re.S).group(1)
        rows = json.loads(blob.replace("<\\/", "</"))
        if len(rows) != len(data) or len(rows) < 100:
            print(json.dumps({"ok": False, "error": f"{page.relative_to(ROOT)} has {len(rows)} laws, data has {len(data)}"}))
            sys.exit(1)

    for note in (
        og_image(ROOT / "docs" / "index.html", ROOT / "docs" / "og-image.png",
                 ".main,.foot{display:none!important}.masthead{padding-block:26px 18px!important}", dark=True),
        og_image(ROOT / "pocket" / "index.html", ROOT / "pocket" / "og-image.png",
                 (".chart-sec,.toolbar,main,.cta-row,.asof{display:none!important}.top{padding-block:24px 6px!important}"
                 ".hero{padding-block:8px 0!important}.hero h1{font-size:4.1rem!important}.fan{height:400px!important}")),
    ):
        if note:
            out["notes"].append(note)

    # 1. This repo.
    why = ready(ROOT)
    if why:
        out["lawbook"] = f"skipped: {why}"
    else:
        git(ROOT, "add", "-A")
        if staged(ROOT):
            git(ROOT, "commit", "-q", "-m", summary + TRAILER)
            git(ROOT, "push", "-q", "origin", "main")
            out["lawbook"] = "pushed " + git(ROOT, "rev-parse", "--short", "HEAD")
        else:
            out["lawbook"] = "no changes"

    # 2. Pocket Lawbook.
    pocket = ROOT / "pocket"
    out["pocket"] = sync(POCKET_REPO, {name: (pocket / name).read_bytes()
                                       for name in ("index.html", "favicon.svg", "apple-touch-icon.png", "og-image.png", ".nojekyll")},
                         summary)

    # 3. The data.maximumnewyork.com mirror.
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert page.count("</body>") == 1
    out["mirror"] = sync(MIRROR_REPO, {
        "public/lawbook/app.html": page.replace("</body>", FRAME_SCRIPT).encode("utf-8"),
        "public/og-lawbook.png": (ROOT / "docs" / "og-image.png").read_bytes(),
    }, f"Lawbook: {summary[0].lower() + summary[1:]}")

    out["ok"] = not any(str(out[k]).startswith("skipped") for k in ("lawbook", "pocket", "mirror"))
    print(json.dumps(out))


if __name__ == "__main__":
    main()
