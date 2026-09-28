# Handoff: Monster price dashboard for my portfolio site

Paste everything below the line into a new Claude Code chat opened in the
portfolio site's directory. Fill in the `<...>` bits first.

---

I want to add a small "Monster Energy price tracker" page to this site as a
portfolio project. This is a Next.js site deployed on Vercel. Before writing
anything, look at how this repo is structured (App Router vs Pages Router,
styling approach, existing components, how other project pages are laid out)
and match those conventions. Don't add new dependencies unless you really
need them; if a chart library is already installed, use it.

## The data source

A separate repo of mine, `Nalomun/MonsterTracker`, scrapes Amazon twice a
day (09:00 and 18:00 UTC) with GitHub Actions and commits a compact summary
file. It's public, so fetch it without auth:

```
https://raw.githubusercontent.com/Nalomun/MonsterTracker/main/dashboard.json
```

Its shape (about 50 KB):

```jsonc
{
  "generated": "2026-09-28T04:44:00+00:00",  // UTC, when the scrape ran
  "ok": true,                                 // false if Amazon blocked the scrape
  "threshold": 0.12,                          // $/fl oz that counts as a "deal"
  "reliable_since": "2026-09-28",             // history before this came from a buggy parser
  "listings_checked": 73,
  "deals": [ { "asin", "title", "price", "fl_oz", "price_per_oz", "seller_info",
               "availability", "offer_type", "sns_price", "verified", "link" } ],
  "best":  [ /* same shape; the 10 cheapest listings this run */ ],
  "daily": [ { "date": "2026-09-28", "best_price_per_oz": 0.0895, "best_asin": "...",
               "best_title": "...", "deals": 6, "listings": 73, "reliable": true } ],
  "products": [ { "asin", "title", "link", "fl_oz", "latest_price", "latest_price_per_oz",
                  "latest_seen", "min_price_per_oz",
                  "series": [["2026-09-01", 0.1124], ["2026-09-02", 0.1124], ...] } ]
}
```

Notes on the data:
- `price_per_oz` is US dollars per fluid ounce. `fl_oz` is the whole pack.
- `offer_type` is `"featured"` (Amazon buy box) or `"third_party"` (cheapest
  marketplace offer; show it but label it).
- `sns_price` is the Subscribe & Save price when it's cheaper, else null.
- `daily` entries with `reliable: false` are from the old scraper and had bad
  prices; either hide them or render them muted/dashed so the chart is honest.
- Do NOT fetch `price_history.json` from that repo; it's large and unbounded.

## How to fetch it

Fetch server-side with ISR so every visitor doesn't hit GitHub:

```ts
const res = await fetch(
  'https://raw.githubusercontent.com/Nalomun/MonsterTracker/main/dashboard.json',
  { next: { revalidate: 1800 } },   // 30 min is plenty; data changes twice a day
);
```

Handle failure gracefully: if the fetch fails or `ok` is false, render the
page with a "data temporarily unavailable" state instead of crashing, and
show the `generated` timestamp as "last updated X hours ago" so it's clear
how fresh the data is. Consider a tiny `/api/monster` route handler only if
the site's structure makes client-side fetching necessary.

## What the page should show

Route: `<e.g. /projects/monster-tracker>`. Link it from `<wherever the other
projects are listed>`.

1. A header with the current status: number of deals at or below the
   threshold, listings checked, and last-updated time.
2. A "current deals" table or card list from `deals` (price, pack size,
   $/fl oz, seller, Subscribe & Save if present, link to Amazon). Empty state
   when there are none: show the `best` list instead with "no deals under
   $0.12/oz right now, cheapest is ...".
3. A line chart of `daily.best_price_per_oz` over time with a horizontal
   line at `threshold`. Muted styling for `reliable: false` points.
4. Optional: small sparklines per product from `products[].series`, or a
   selector to view one product's history.
5. A short "how it works" blurb: Python + Playwright scraper on GitHub
   Actions, commits JSON to the repo, this page reads it with ISR. Link to
   `https://github.com/Nalomun/MonsterTracker`.

Style preferences: `<dark/light, accent colour, fonts, tone — match the rest
of the site>`. Keep it responsive; the table should collapse sensibly on
phones.

## Definition of done

- `npm run build` (or whatever this repo uses) passes with no type errors.
- Page renders with real data locally and with the fetch mocked to fail.
- Show me the page running before you finish.
