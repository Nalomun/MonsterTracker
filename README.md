# Monster Energy Deal Tracker 🔋⚡

Scrapes Amazon twice a day for Monster Energy multi-packs, works out the
price per fluid ounce, and opens a GitHub Issue when something is at or
below the threshold (default **$0.12 / fl oz**).

## How it works

1. `tracker.py` loads a few pages of Amazon search results in a headless
   Chromium browser (Playwright). Amazon serves an empty anti-bot page to
   plain HTTP clients most of the time, but a real browser gets through.
   Every request uses a fresh browser context and blocked responses are
   retried with back-off.
2. Each search result card already contains the ASIN, title, featured
   price, Amazon's own "$x.xx / fluid ounce" and the stock / offer status,
   so every Monster listing on those pages gets priced without opening its
   product page.
3. The can size and pack count are parsed from the title
   (`16 Ounce (Pack of 15)`, `473 mL Cans, 12 Pack`, `16 Oz (24-Pack)`, ...)
   and cross-checked against Amazon's unit price. Listings where the two
   disagree are flagged (⚠️) and never alerted on unless verified.
4. Deal candidates are re-checked on their product page (buy-box price,
   seller, availability, Subscribe & Save price) before they are reported.
5. Output:
   - `deal_report.md` – latest report
   - `price_history.json` – every priced listing from every run
   - `current_deals.json` – state used by the workflow to tell new deals
     from ones already alerted

The GitHub Action opens a **new** issue only when a deal appears that was
not in the previous run (or got ≥3% cheaper), and closes the issue it
opened before. When the deals are unchanged it just refreshes the open
issue's body. If Amazon blocks the scrape, nothing is committed and no
issue is touched; the job fails visibly instead.

## Setup

1. Push this repo to GitHub.
2. **Settings → Actions → General → Workflow permissions**: choose
   *Read and write permissions* and save.
3. Run the workflow once from the **Actions** tab (*Monster Deal Tracker →
   Run workflow*) to check it gets through Amazon from GitHub's runners.

## Configuration

Everything is an environment variable (set in `.github/workflows/tracker.yml`
or in your shell):

| Variable | Default | Meaning |
|---|---|---|
| `PRICE_THRESHOLD` | `0.12` | $/fl oz that counts as a deal |
| `MIN_FL_OZ` | `64` | ignore packs smaller than this (4 × 16 oz) |
| `MAX_PAGES` | `3` | search result pages per query |
| `SEARCH_QUERIES` | `monster energy drink` | `\|`-separated Amazon searches |
| `VERIFY_DEALS` | `1` | `0` skips product-page verification of deals |
| `USE_BROWSER` | `1` | `0` forces plain HTTP (usually blocked by Amazon) |
| `DEBUG_HTML` | unset | `1` saves every fetched page under `debug_html/` |

The schedule lives in `.github/workflows/tracker.yml`:

```yaml
schedule:
  - cron: '0 9,18 * * *'
```

## Running locally

```bash
pip install -r requirements.txt
playwright install chromium
python tracker.py
```

A run takes a few minutes because of the polite delays between requests.

Tests (no network needed):

```bash
python -m pytest -q tests
```

## Notes

- Amazon's own unit price is not always per fluid ounce (some listings
  show `$1.80/count`), so the title-derived pack size is used whenever it
  parses, and the unit price only as a fallback or a sanity check.
- Listings with "No featured offers available" are priced from the
  cheapest third-party offer and marked as such in the report.
- Out-of-stock listings are recorded in the history but never alerted on.
- Results depend on Amazon's HTML; if the layout changes, the parsers in
  `tracker.py` (`parse_search_cards`, `parse_product_page`) are the place
  to look. Run with `DEBUG_HTML=1` to capture what Amazon served.

## License

MIT
