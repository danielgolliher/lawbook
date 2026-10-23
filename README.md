# 119th Congress Lawbook

An explorer for every public law of the 119th Congress.

- Live site: https://danielgolliher.github.io/lawbook/ (GitHub Pages, served from `docs/` on `main`)
- Mirror: https://data.maximumnewyork.com/lawbook (copy at `public/lawbook/app.html` in danielgolliher/nyc-budget-graphics; re-copy `docs/index.html` there after changes)
- Pocket Lawbook (phone edition): https://danielgolliher.github.io/pocket-lawbook/ (repo danielgolliher/pocket-lawbook, checkout at ~/Downloads/pocket-lawbook; built here from `pocket.html` into `pocket/` and copied over by `publish.py`)
- Claude artifact: https://claude.ai/artifact/7HksxYg14Y8rxaKweLp2r2 (a snapshot from Oct. 22, 2026; the weekly refresh doesn't update it)

`app.html` and `pocket.html` are the page templates. `scripts/build_page.py` builds `docs/index.html` (the Lawbook site), `pocket/index.html` (Pocket Lawbook) and a root `index.html` used for the artifact (not committed). `data/laws.json` is the app data. `raw/` holds the downloaded source files (not committed; about 66 MB, re-downloadable).

## Refresh with new laws

A weekly scheduled task in the Claude desktop app ("Refresh 119th Congress Lawbook", Mondays 9 AM) does this automatically. To run it by hand:

```bash
cd ~/Downloads/public-laws-119
python3 -I scripts/refresh.py                 # download new laws and updated records, rebuild, print a JSON report
# if the report lists "unreviewed" or "needsLabel" laws, add them to KIND / LABEL in scripts/build_data.py, then:
python3 -I scripts/refresh.py --offline       # rebuild from raw/ without downloading
python3 -I scripts/publish.py "Weekly refresh: ..."   # push this repo, pocket-lawbook and the data.maximumnewyork.com mirror
```

`refresh.py` refuses to shrink the law count. New laws build even before GovInfo posts their text or CRS writes a summary: they default to "Policy change", show their official title as the summary line, and fill in on later runs. `publish.py` re-renders both social preview images, then commits and pushes only its own changes; it skips a repo that has unpushed commits or can't fast-forward. Set `CONGRESS_API_KEY` to use your own api.data.gov key instead of `DEMO_KEY`.

Sources: Congress.gov API (law list), GovInfo BILLSTATUS bulk XML (histories, sponsors, CRS summaries), GovInfo enrolled bills and slip laws (word counts, Stat. citations, long titles), House Clerk and Senate roll-call XML (party splits). congress.gov pages block curl; the API and GovInfo do not.
