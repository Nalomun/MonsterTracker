# Monster Energy Deal Tracker

A small price-tracking pipeline that checks Amazon twice a day for Monster
Energy multi-packs, works out the price per fluid ounce for each listing, and
opens a GitHub Issue when something drops to $0.12/fl oz or lower. It runs
entirely on GitHub Actions and costs nothing to operate.

I built this because I drink a lot of Monster and got tired of checking
Amazon by hand. It has also turned into a decent exercise in keeping a
scraper alive against a site that actively tries to block scrapers.

**Live output:** [`deal_report.md`](deal_report.md) is regenerated on every
run. [`dashboard.json`](dashboard.json) is a compact feed built for the
dashboard on my portfolio site.

## How it works

```
GitHub Actions (09:00 / 18:00 UTC)
  └─ tracker.py
       ├─ headless Chromium fetches 3 pages of Amazon search results
       ├─ parses every Monster listing: price, pack size, $/fl oz, stock
       ├─ re-checks deal candidates on their product page
       ├─ appends to price_history.json, writes deal_report.md, dashboard.json
       └─ current_deals.json → workflow opens/updates an Issue only if a new deal appeared
```

**Fetching.** Amazon serves an empty anti-bot page to plain HTTP clients
almost every time, so pages are loaded in a real headless browser
(Playwright). Each request gets a fresh browser context, there are randomised
delays between requests, and blocked responses are retried with back-off.
If the browser is unavailable the tracker falls back to `requests`.

**Pricing from search results.** A search result card already carries the
ASIN, full title, featured price, Amazon's own unit price and the stock or
offer status. Reading those means every Monster listing on the results pages
gets priced with three requests, instead of opening 100+ product pages. It
also avoids the trap the first version of this project fell into: pulling a
price from a product page and getting the "lower-priced alternative" widget
instead of the buy box.

**Pack size.** Total fluid ounces are parsed from the title and its variant
text, which comes in a lot of forms (`16 Ounce (Pack of 15)`, `16 Fl Oz |
Pack of 12`, `473 mL Cans, 12 Pack`, `16 Oz (24-Pack)`, bundles like
`Pack of 15 + Pack of 15`). The result is cross-checked against Amazon's
unit price. Amazon's figure is not trustworthy on its own (some listings
show `$1.80/count` or a per-ounce price that is off by 10x), so it is only a
fallback and a sanity check. Listings where the two disagree are flagged and
never alerted on.

**Verification.** Anything at or below the threshold is re-checked on its
product page for the buy-box price, seller, availability and Subscribe &
Save price before it goes in the report.

**Alerting.** The workflow keeps one open Issue. It opens a new one only when
a deal appears that was not there last run (or got at least 3% cheaper),
closes the previous one, and otherwise just refreshes the body. If Amazon
blocks the scrape, nothing is committed, no Issue is touched, and the job
fails so it shows up red.

## Setup

1. Fork or clone, then push to your own GitHub repo.
2. **Settings → Actions → General → Workflow permissions**: select
   *Read and write permissions*.
3. Trigger the workflow once from the Actions tab to confirm the runner can
   get through to Amazon.

## Configuration

All settings are environment variables, set in
`.github/workflows/tracker.yml` or in your shell.

| Variable | Default | Meaning |
|---|---|---|
| `PRICE_THRESHOLD` | `0.12` | $/fl oz that counts as a deal |
| `MIN_FL_OZ` | `64` | ignore packs smaller than this (4 × 16 oz) |
| `MAX_PAGES` | `3` | search result pages per query |
| `SEARCH_QUERIES` | `monster energy drink` | `\|`-separated Amazon searches |
| `VERIFY_DEALS` | `1` | `0` skips product-page verification |
| `USE_BROWSER` | `1` | `0` forces plain HTTP (usually blocked) |
| `DEBUG_HTML` | unset | `1` saves every fetched page under `debug_html/` |

Schedule (cron, UTC) is at the top of the workflow file.

## Running locally

```bash
pip install -r requirements.txt
playwright install chromium
python tracker.py
```

A run takes three to five minutes because of the deliberate delays between
requests. Unit tests cover the title parsing, search-card parsing, product
page parsing and deal logic, and need no network:

```bash
python -m pytest -q tests
```

## Output files

| File | Purpose |
|---|---|
| `deal_report.md` | Human-readable report from the latest run |
| `current_deals.json` | Latest deals plus which ones are new; used by the workflow |
| `dashboard.json` | Compact feed for a website (see below) |
| `price_history.json` | Every priced listing from every run, append-only |

### `dashboard.json`

About 50 KB, regenerated every run, fetchable without auth from

```
https://raw.githubusercontent.com/Nalomun/MonsterTracker/main/dashboard.json
```

```jsonc
{
  "generated": "2026-09-28T04:44:00+00:00",  // UTC
  "ok": true,                                 // false if the scrape was blocked
  "threshold": 0.12,
  "reliable_since": "2026-09-28",             // earlier history used the old parser
  "listings_checked": 73,
  "deals": [ { "asin", "title", "price", "fl_oz", "price_per_oz", "seller_info",
               "availability", "offer_type", "sns_price", "verified", "link" } ],
  "best":  [ /* same shape; 10 cheapest listings this run */ ],
  "daily": [ { "date", "best_price_per_oz", "best_asin", "best_title",
               "deals", "listings", "reliable" } ],                 // up to 120 days
  "products": [ { "asin", "title", "link", "fl_oz", "latest_price",
                  "latest_price_per_oz", "latest_seen", "min_price_per_oz",
                  "series": [["2026-09-01", 0.1124], ...] } ]      // 15 most-seen, 90 days
}
```

Don't point a website at `price_history.json`; it grows by roughly 40 KB per
run.

## Known limitations

- Amazon's HTML changes. The parsers live in `parse_search_cards` and
  `parse_product_page` in `tracker.py`; run with `DEBUG_HTML=1` to capture
  what was served when something breaks.
- Search results vary by session and region, so the set of listings differs
  a little from run to run.
- Listings with no featured offer are priced from the cheapest third-party
  offer and labelled as such. Out-of-stock listings are recorded but never
  alerted on.
- History before 2026-09-28 was collected by an earlier version with a buggy
  price parser and should not be trusted; `dashboard.json` flags those days.

## License

MIT
