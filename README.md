# 119th Congress Lawbook

An explorer for every public law of the 119th Congress.

- Live site: https://danielgolliher.github.io/lawbook/ (GitHub Pages, served from `docs/` on `main`)
- Mirror: https://data.maximumnewyork.com/lawbook (copy at `public/lawbook/app.html` in danielgolliher/nyc-budget-graphics; re-copy `docs/index.html` there after changes)
- Claude artifact: https://claude.ai/artifact/7HksxYg14Y8rxaKweLp2r2

`app.html` is the page template. `scripts/build_page.py` builds `docs/index.html` (the website) and a root `index.html` used for the artifact (not committed). `data/laws.json` is the app data. `raw/` holds the downloaded source files (not committed; about 66 MB, re-downloadable).

## Refresh with new laws

```bash
cd ~/Downloads/public-laws-119
curl -s -o raw/api_law.json "https://api.congress.gov/v3/law/119?api_key=DEMO_KEY&limit=250&format=json"
# then download BILLSTATUS XML, roll calls and enacted text for any new laws (see the commands in this project's history),
python3 -I scripts/extract.py raw/api_law.json raw/billstatus data/laws_base.json
python3 -I scripts/enrich.py data/laws_base.json raw/votes raw/text data/laws_enriched.json
python3 -I scripts/build_data.py data/laws_enriched.json data/laws.json
python3 -I scripts/build_page.py
```

Update `TODAY` in `app.html`, and add any new law to `KIND` (and `LABEL` if it has no short title) in `scripts/build_data.py`; the build fails if a law has no summary sentence.

Sources: Congress.gov API (law list), GovInfo BILLSTATUS bulk XML (histories, sponsors, CRS summaries), GovInfo enrolled bills and slip laws (word counts, Stat. citations, long titles), House Clerk and Senate roll-call XML (party splits). congress.gov pages block curl; the API and GovInfo do not.
