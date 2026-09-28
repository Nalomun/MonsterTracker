"""Monster Energy deal tracker.

Scrapes Amazon search results for Monster Energy drinks, works out the
price per fluid ounce for each multi-pack, and reports anything at or
below the price threshold.

How it works
------------
1. Fetch a few pages of Amazon search results in a real (headless)
   browser.  The search result cards already carry the ASIN, full title,
   featured price, Amazon's own unit price and the stock / offer status,
   so no per-product page is needed to price a listing.  This is far
   fewer requests than opening every product page and is much harder
   for Amazon to block.
2. Parse the can size and pack count out of the title to get total
   fluid ounces, cross-checked against Amazon's own "$x.xx / fluid ounce".
3. Anything at or below the threshold is a deal candidate.  Candidates
   are re-checked on their product page (buy box price, seller,
   availability, Subscribe & Save) so a search-page glitch can't fire
   an alert.
4. Results are appended to price_history.json, a markdown report is
   written to deal_report.md, and current_deals.json holds the state the
   GitHub Action uses to decide whether a *new* deal appeared.

Configuration is via environment variables (all optional):
    PRICE_THRESHOLD   $/fl oz that counts as a deal          (default 0.12)
    MIN_FL_OZ         ignore listings smaller than this      (default 64)
    MAX_PAGES         search result pages per query          (default 3)
    SEARCH_QUERIES    '|'-separated Amazon search queries
    VERIFY_DEALS      '0' to skip product-page verification  (default 1)
    USE_BROWSER       '0' to force plain HTTP instead of Playwright
    DEBUG_HTML        '1' to save fetched pages to debug_html/
"""

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

try:  # Playwright is optional; plain requests is the fallback.
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


HISTORY_FILE = 'price_history.json'
REPORT_FILE = 'deal_report.md'
STATE_FILE = 'current_deals.json'

ML_PER_FL_OZ = 29.5735

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0',
]


def log(msg=''):
    print(msg, flush=True)


def env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return int(default)


def parse_money(text):
    """'$1,234.56' -> 1234.56, or None."""
    if not text:
        return None
    m = re.search(r'\$?\s*([\d,]+(?:\.\d+)?)', text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(',', ''))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Title parsing
# ---------------------------------------------------------------------------

_SIZE_OZ = re.compile(
    r'(\d+(?:\.\d+)?)\s*-?\s*(?:fl\.?\s*oz\b|fluid\s*ounces?|ounces?|oz\b)', re.I)
_SIZE_ML = re.compile(r'(\d+(?:\.\d+)?)\s*-?\s*m[lL]\b')
_NET_TOTAL = re.compile(r'net\s*wt\.?\s*(\d+(?:\.\d+)?)\s*(?:fl\.?\s*)?(?:oz|ounces?)', re.I)
_COUNT_PATTERNS = [
    re.compile(r'pack\s*of\s*(\d+)', re.I),
    re.compile(r'\b(\d+)\s*-?\s*(?:pack|pk)\b', re.I),
    re.compile(r'\b(\d+)\s*-?\s*cans?\b', re.I),
    re.compile(r'\b(\d+)\s*-?\s*(?:count|ct)\b', re.I),
]


def extract_fluid_oz(text):
    """Total fluid ounces described by a product title, or None.

    Handles the common Amazon phrasings:
      "16 Ounce (Pack of 15)", "16 Fl Oz | Pack of 12", "24 x 16 fl oz",
      "473 mL Cans, 12 Pack", "16oz (24-Pack)", "6 Pack, 72 Ounce",
      "24 ounce cans with Resealable Lids (Mega Monster, 12 Cans)".
    """
    if not text:
        return None

    m = _NET_TOTAL.search(text)
    if m:
        return float(m.group(1))

    # Can size: first ounce/ml figure that looks like a single can (<= 32 oz).
    size = None
    total_hint = None
    for m in _SIZE_OZ.finditer(text):
        val = float(m.group(1))
        if 4 <= val <= 32 and size is None:
            size = val
        elif val > 32 and total_hint is None:
            total_hint = val
    if size is None:
        for m in _SIZE_ML.finditer(text):
            val = float(m.group(1)) / ML_PER_FL_OZ
            if 4 <= val <= 32:
                size = round(val, 2)
                break

    # Pack count.  "24 Pack (Pack of 4)" is 96 cans (a case of packs), but
    # bundles read "Pack of 15 + Pack of 15 | Bundle (Pack of 30)", where the
    # largest figure is already the total, and "6 pack (6 pack)" is just 6.
    pack_of = sorted({int(m.group(1)) for m in _COUNT_PATTERNS[0].finditer(text)
                      if 1 <= int(m.group(1)) <= 96})
    other = []
    for pat in _COUNT_PATTERNS[1:]:
        other += [int(m.group(1)) for m in pat.finditer(text) if 1 <= int(m.group(1)) <= 96]
    if len(pack_of) == 1 and other and pack_of[0] != max(other) and '+' not in text:
        count = pack_of[0] * max(other)
    elif pack_of:
        count = max(pack_of)
    elif other:
        count = max(other)
    else:
        count = None

    if size is not None and count:
        return round(size * count, 2)
    if total_hint is not None:
        return total_hint
    if size is not None:
        return size  # single can
    return None


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

class BlockedError(Exception):
    pass


def looks_blocked(html):
    """True for Amazon's captcha / 'Sorry' / blank anti-bot pages."""
    if not html or len(html) < 20000:
        return True
    head = html[:4000]
    if 'validateCaptcha' in head or 'api-services-support@amazon.com' in head:
        # The comment appears on real pages too, so only treat it as a
        # block when there is no real content behind it.
        if 's-search-result' not in html and 'productTitle' not in html:
            return True
    lowered = head.lower()
    return ('sorry! something went wrong' in lowered
            or 'robot check' in lowered
            or 'enter the characters you see below' in lowered)


class Fetcher:
    """Fetches Amazon pages with a headless browser, falling back to requests.

    A fresh browser context (fresh cookies) is used for every request and
    blocked responses are retried with growing back-off.
    """

    def __init__(self, use_browser=True, debug_dir=None):
        self.use_browser = use_browser and sync_playwright is not None
        self.debug_dir = debug_dir
        self._pw = None
        self._browser = None
        if use_browser and sync_playwright is None:
            log('  (playwright not installed, using plain HTTP)')

    def __enter__(self):
        if self.use_browser:
            try:
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.launch(headless=True)
            except Exception as e:  # browser missing etc.
                log(f'  (could not start browser: {e}; using plain HTTP)')
                self.use_browser = False
                self._pw = None
        return self

    def __exit__(self, *exc):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def _browser_get(self, url):
        ua = random.choice(USER_AGENTS)
        context = self._browser.new_context(
            user_agent=ua, viewport={'width': 1366, 'height': 900}, locale='en-US')
        try:
            context.route(
                '**/*',
                lambda route: route.abort()
                if route.request.resource_type in ('image', 'media', 'font')
                else route.continue_())
            page = context.new_page()
            page.goto(url, wait_until='domcontentloaded', timeout=60000,
                      referer='https://www.amazon.com/')
            page.wait_for_timeout(1500)
            return page.content()
        finally:
            context.close()

    def _requests_get(self, url):
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            raise BlockedError(f'HTTP {r.status_code}')
        return r.text

    def get(self, url, label='page', attempts=3):
        """Return page HTML or None if every attempt was blocked."""
        for attempt in range(1, attempts + 1):
            try:
                html = self._browser_get(url) if self.use_browser else self._requests_get(url)
                if looks_blocked(html):
                    raise BlockedError('anti-bot page')
                if self.debug_dir:
                    os.makedirs(self.debug_dir, exist_ok=True)
                    safe = re.sub(r'[^A-Za-z0-9]+', '_', label)[:60]
                    with open(os.path.join(self.debug_dir, safe + '.html'), 'w', encoding='utf-8') as f:
                        f.write(html)
                return html
            except Exception as e:
                wait = 8 * attempt + random.uniform(0, 5)
                log(f'  {label}: attempt {attempt}/{attempts} failed ({e}); '
                    f'{"retrying in %.0fs" % wait if attempt < attempts else "giving up"}')
                if attempt < attempts:
                    time.sleep(wait)
        return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def extract_card_title(card):
    """Full product title of a search result card.

    Newer Amazon layouts put the brand in the <h2> and the rest of the
    title in the following link; older ones put everything in the <h2>.
    The image alt text is a last resort because it is truncated.
    """
    title_block = card.select_one('[data-cy="title-recipe"]') or card
    h2 = title_block.find('h2')
    h2_text = h2.get_text(' ', strip=True) if h2 else ''
    link = title_block.select_one('a.a-link-normal.s-link-style.a-text-normal')
    link_text = link.get_text(' ', strip=True) if link else ''
    if link_text and h2_text and not link_text.lower().startswith(h2_text.lower()):
        title = f'{h2_text} {link_text}'
    else:
        title = link_text or h2_text
    if not title:
        img = card.select_one('img.s-image')
        title = (img.get('alt') or '').strip() if img else ''
    title = re.sub(r'^sponsored ad\s*-\s*', '', title, flags=re.I)
    return re.sub(r'\s+', ' ', title).strip()


def parse_search_cards(html):
    """Parse an Amazon search results page into a list of listing dicts."""
    soup = BeautifulSoup(html, 'lxml')
    listings = []
    for card in soup.find_all('div', {'data-component-type': 's-search-result'}):
        asin = card.get('data-asin')
        if not asin:
            continue

        title = extract_card_title(card)
        if not title:
            continue
        # Size / variant text shown under the title, e.g. "Pack of 15" when
        # the title itself is truncated to "..., 16 Ounce".
        title_block = card.select_one('[data-cy="title-recipe"]')
        variant = ''
        if title_block:
            full = re.sub(r'\s+', ' ', title_block.get_text(' ', strip=True))
            variant = full.replace(title, '', 1).strip(' |,-')

        text = card.get_text(' ', strip=True)
        sponsored = bool(re.search(r'\bSponsored\b', text))

        price = None
        offer_type = None
        price_block = card.select_one('[data-cy="price-recipe"]') or card
        off = price_block.select_one('.a-price:not(.a-text-price) .a-offscreen')
        if off:
            price = parse_money(off.get_text())
            if price is not None:
                offer_type = 'featured'

        # Amazon's own unit price, e.g. "( $0.09 $0.09/fluid ounce)".
        unit_price = None
        unit = None
        m = re.search(r'\$\s*(\d+\.\d+)\s*/\s*(fluid\s*ounce|fl\s*oz|ounce|count|item|oz)',
                      text, re.I)
        if m:
            unit_price = float(m.group(1))
            unit = m.group(2).lower()

        # "No featured offers available $42.00 (10 new offers)" or
        # "More Buying Choices $37.00 (4 new offers)".
        secondary = card.select_one('[data-cy="secondary-offer-recipe"]')
        other_offer_price = None
        other_offer_count = None
        if secondary:
            stext = secondary.get_text(' ', strip=True)
            om = re.search(r'\$([\d,]+\.\d{2})', stext)
            if om:
                other_offer_price = parse_money(om.group(0))
            cm = re.search(r'\((\d+)\s+(?:new|used)', stext)
            if cm:
                other_offer_count = int(cm.group(1))
            if price is None and other_offer_price is not None:
                price = other_offer_price
                offer_type = 'third_party'

        out_of_stock = 'out of stock' in text.lower() or 'currently unavailable' in text.lower()

        listings.append({
            'asin': asin,
            'title': title,
            'variant': variant,
            'price': price,
            'offer_type': offer_type,
            'amazon_unit_price': unit_price,
            'amazon_unit': unit,
            'other_offer_price': other_offer_price,
            'other_offer_count': other_offer_count,
            'out_of_stock': out_of_stock,
            'sponsored': sponsored,
        })
    return listings


def parse_product_page(html):
    """Pull buy-box details off a product page.  Any field may be None."""
    soup = BeautifulSoup(html, 'lxml')

    def text_of(sel):
        el = soup.select_one(sel)
        return re.sub(r'\s+', ' ', el.get_text(' ', strip=True)) if el else None

    title = text_of('#productTitle')

    price = None
    for sel in ('#corePrice_feature_div .a-price:not(.a-text-price) .a-offscreen',
                '#corePriceDisplay_desktop_feature_div .a-price:not(.a-text-price) .a-offscreen',
                '#apex_desktop .a-price:not(.a-text-price) .a-offscreen',
                '#price_inside_buybox',
                '#buybox .a-price .a-offscreen'):
        for el in soup.select(sel):
            v = parse_money(el.get_text())
            if v is not None and v >= 3:  # skip unit prices like "$0.09"
                price = v
                break
        if price is not None:
            break

    sns_price = None
    for el in soup.select('#snsAccordionRowMiddle .a-price .a-offscreen, #sns-base-price'):
        v = parse_money(el.get_text())
        if v is not None and v >= 3:
            sns_price = v
            break

    availability = text_of('#availability') or ''
    if not availability and soup.select_one('#buybox-see-all-buying-choices'):
        availability = 'No featured offer (see all buying options)'

    seller = None
    for sel in ('#merchantInfoFeature_feature_div .offer-display-feature-text-message',
                '[offer-display-feature-name="desktop-merchant-info"] .offer-display-feature-text-message',
                '#sellerProfileTriggerId', '#merchant-info', '#merchantInfo'):
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            seller = re.sub(r'\s+', ' ', el.get_text(' ', strip=True))
            seller = re.sub(r'^(shipper|sold by|ships from)\s*/?\s*(seller)?\s*', '', seller, flags=re.I)
            break

    unit_price = None
    core = text_of('#corePrice_feature_div') or ''
    m = re.search(r'\$\s*(\d+\.\d+)\s*(?:per|/)\s*(?:fluid\s*ounce|fl\s*oz)', core, re.I)
    if m:
        unit_price = float(m.group(1))

    return {
        'title': title,
        'price': price,
        'sns_price': sns_price,
        'availability': availability,
        'seller': seller,
        'amazon_unit_price': unit_price,
    }


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

class MonsterDealTracker:
    def __init__(self):
        self.price_threshold = env_float('PRICE_THRESHOLD', 0.12)
        self.min_fl_oz = env_float('MIN_FL_OZ', 64)
        self.max_pages = env_int('MAX_PAGES', 3)
        self.queries = [q.strip() for q in
                        os.environ.get('SEARCH_QUERIES', 'monster energy drink').split('|') if q.strip()]
        self.verify = os.environ.get('VERIFY_DEALS', '1') != '0'
        self.use_browser = os.environ.get('USE_BROWSER', '1') != '0'
        self.debug_dir = 'debug_html' if os.environ.get('DEBUG_HTML') == '1' else None
        self.results = []
        self.pages_fetched = 0
        self.pages_failed = 0

    # -- collection -------------------------------------------------------

    def search_amazon(self, fetcher):
        """Fetch search pages and turn Monster listings into results."""
        seen = set()
        for query in self.queries:
            log(f'\n🔍 Searching Amazon for "{query}"...')
            for page_no in range(1, self.max_pages + 1):
                if page_no > 1 or self.pages_fetched:
                    time.sleep(random.uniform(5, 10))
                url = f'https://www.amazon.com/s?k={requests.utils.quote(query)}&page={page_no}'
                html = fetcher.get(url, label=f'search "{query}" page {page_no}')
                if html is None:
                    self.pages_failed += 1
                    continue
                self.pages_fetched += 1
                cards = parse_search_cards(html)
                if not cards:
                    log(f'  Page {page_no}: no product cards found (layout change?)')
                    self.pages_failed += 1
                    continue
                added = 0
                for card in cards:
                    if card['asin'] in seen:
                        continue
                    seen.add(card['asin'])
                    result = self.build_result(card)
                    if result:
                        self.results.append(result)
                        added += 1
                log(f'  Page {page_no}: {len(cards)} cards, {added} Monster multi-packs priced')
        log(f'\n📦 {len(self.results)} Monster listings priced from '
            f'{self.pages_fetched} page(s) ({self.pages_failed} failed)')

    def build_result(self, card):
        title = card['title']
        if 'monster' not in title.lower():
            return None
        if card['price'] is None:
            return None

        fl_oz = extract_fluid_oz(title)
        source = 'title'
        variant = card.get('variant') or ''
        if (fl_oz is None or fl_oz < self.min_fl_oz) and variant:
            with_variant = extract_fluid_oz(f'{title} {variant}')
            if with_variant and with_variant >= self.min_fl_oz:
                fl_oz = with_variant
                title = f'{title} ({variant})'
                source = 'title+variant'
        unit_ok = card['amazon_unit'] in ('fluid ounce', 'fl oz', 'ounce', 'oz')
        amazon_ppo = card['amazon_unit_price'] if unit_ok else None
        amazon_fl_oz = None
        if amazon_ppo and 0.03 <= amazon_ppo <= 1.0:
            amazon_fl_oz = round(card['price'] / amazon_ppo, 1)
        # Fall back to Amazon's unit price when the title gives no pack
        # size (or is truncated and only shows the can size).
        if (fl_oz is None or fl_oz < self.min_fl_oz) and amazon_fl_oz and amazon_fl_oz >= self.min_fl_oz:
            fl_oz = amazon_fl_oz
            source = 'amazon_unit_price'
        if not fl_oz or fl_oz < self.min_fl_oz:
            return None

        price_per_oz = card['price'] / fl_oz
        # Amazon's unit price is rounded to the cent, so allow slack.  A big
        # disagreement usually means the title was parsed wrong.
        mismatch = bool(amazon_ppo and source != 'amazon_unit_price'
                        and abs(amazon_ppo - price_per_oz) > max(0.015, 0.25 * price_per_oz))

        result = {
            'retailer': 'Amazon',
            'asin': card['asin'],
            'title': title,
            'price': card['price'],
            'fl_oz': fl_oz,
            'fl_oz_source': source,
            # Amazon's unit price is rounded to the cent, so a size derived
            # from it is only approximate.
            'fl_oz_estimated': source == 'amazon_unit_price',
            'price_per_oz': round(price_per_oz, 4),
            'amazon_unit_price': amazon_ppo,
            'unit_price_mismatch': mismatch,
            'offer_type': card['offer_type'],
            'other_offer_price': card['other_offer_price'],
            'other_offer_count': card['other_offer_count'],
            'availability': 'Out of Stock' if card['out_of_stock'] else 'In Stock',
            'sponsored': card['sponsored'],
            'seller_info': 'Amazon featured offer' if card['offer_type'] == 'featured'
                           else f'Third-party ({card["other_offer_count"] or "?"} offers, lowest)',
            'verified': False,
            'link': f'https://www.amazon.com/dp/{card["asin"]}',
            'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }
        return result

    # -- verification -----------------------------------------------------

    def verify_deals(self, fetcher, max_items=15):
        """Re-check deal candidates on their product page."""
        candidates = sorted(self.find_deals(include_unverified=True),
                            key=lambda r: r['price_per_oz'])[:max_items]
        if not candidates:
            return
        log(f'\n🔎 Verifying {len(candidates)} deal candidate(s) on their product pages...')
        for r in candidates:
            time.sleep(random.uniform(5, 9))
            html = fetcher.get(r['link'], label=f'product {r["asin"]}')
            if html is None:
                log(f'  {r["asin"]}: could not load product page, keeping search-page price')
                continue
            info = parse_product_page(html)
            r['verified'] = True
            if info['title']:
                page_fl_oz = extract_fluid_oz(info['title'])
                if page_fl_oz and page_fl_oz >= self.min_fl_oz and (
                        r['fl_oz_estimated'] or abs(page_fl_oz - r['fl_oz']) > 0.5):
                    log(f'  {r["asin"]}: product title gives {page_fl_oz:g} fl oz '
                        f'(search-page estimate was {r["fl_oz"]:g})')
                    r['fl_oz'] = page_fl_oz
                    r['fl_oz_source'] = 'product_title'
                    r['fl_oz_estimated'] = False
                    r['title'] = info['title']
                    r['price_per_oz'] = round(r['price'] / r['fl_oz'], 4)
            r['verify_price'] = info['price']
            r['sns_price'] = info['sns_price']
            if info['seller']:
                r['seller_info'] = info['seller']
            if info['availability']:
                r['availability'] = info['availability']
            if info['price'] is not None:
                if abs(info['price'] - r['price']) > 0.01:
                    log(f'  {r["asin"]}: search said ${r["price"]:.2f}, product page says '
                        f'${info["price"]:.2f}; using product page')
                    r['price'] = info['price']
                    r['price_per_oz'] = round(info['price'] / r['fl_oz'], 4)
                # The product page's own $/fl oz settles any title-vs-unit-price doubt.
                if info['amazon_unit_price']:
                    page_ppo = info['amazon_unit_price']
                    r['unit_price_mismatch'] = abs(page_ppo - r['price_per_oz']) > max(0.015, 0.25 * r['price_per_oz'])
                    if r['unit_price_mismatch']:
                        log(f'  {r["asin"]}: product page says ${page_ppo:.2f}/oz but title implies '
                            f'${r["price_per_oz"]:.4f}/oz; excluding')
            elif info['price'] is None and r['offer_type'] == 'featured':
                log(f'  {r["asin"]}: no buy-box price on product page; marking unverified')
                r['verified'] = False
                r['verify_note'] = 'no buy box price on product page'
            status = '⭐' if r['price_per_oz'] <= self.price_threshold else '  '
            log(f'  {status} {r["asin"]} ${r["price_per_oz"]:.4f}/oz  {r["availability"]}  '
                f'{r["seller_info"]}  {r["title"][:50]}')

    # -- reporting --------------------------------------------------------

    def find_deals(self, include_unverified=False):
        deals = []
        for r in self.results:
            if r['price_per_oz'] > self.price_threshold:
                continue
            if r['availability'].lower().startswith('out of stock'):
                continue
            if r['unit_price_mismatch'] and not include_unverified:
                continue
            # A size estimated from Amazon's rounded unit price can be off by
            # half a cent per ounce; only count it when clearly below.
            if r['fl_oz_estimated'] and not include_unverified \
                    and r['price_per_oz'] + 0.006 > self.price_threshold:
                continue
            deals.append(r)
        return sorted(deals, key=lambda r: r['price_per_oz'])

    def save_history(self, filename=HISTORY_FILE):
        history = []
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                try:
                    history = json.load(f)
                except json.JSONDecodeError:
                    history = []
        history.extend(self.results)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=1)
        log(f'\n💾 Appended {len(self.results)} results to {filename} ({len(history)} total)')

    def load_previous_state(self, filename=STATE_FILE):
        if not os.path.exists(filename):
            return {}
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {d['asin']: d for d in data.get('deals', [])}
        except (json.JSONDecodeError, KeyError, TypeError):
            return {}

    def save_state(self, deals, ok, filename=STATE_FILE):
        previous = self.load_previous_state(filename)
        new_deals = []
        for d in deals:
            prev = previous.get(d['asin'])
            if prev is None or d['price_per_oz'] < prev['price_per_oz'] * 0.97:
                new_deals.append(d['asin'])
        state = {
            'ok': ok,
            'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'threshold': self.price_threshold,
            'listings_checked': len(self.results),
            'deals': deals,
            'new_deal_asins': new_deals,
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=1)
        return new_deals

    def generate_report(self, deals, new_deal_asins=()):
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        report = '# Monster Energy Deal Report\n\n'
        report += f'**Generated:** {now}  \n'
        report += f'**Threshold:** ${self.price_threshold:.3f}/fl oz  \n'
        report += f'**Listings priced:** {len(self.results)}\n\n'

        if deals:
            report += f'## 🎉 {len(deals)} deal(s) at or below ${self.price_threshold:.2f}/fl oz\n\n'
            report += '| $/fl oz | Price | Size | Product | Seller | Notes |\n|---|---|---|---|---|---|\n'
            for d in deals:
                notes = []
                if d['asin'] in new_deal_asins:
                    notes.append('🆕 new')
                if d['offer_type'] == 'third_party':
                    notes.append('third-party offer, not the buy box')
                if not d['verified']:
                    notes.append('unverified')
                if d.get('sns_price') and d['sns_price'] < d['price']:
                    notes.append(f'S&S ${d["sns_price"]:.2f} (${d["sns_price"] / d["fl_oz"]:.4f}/oz)')
                if 'in stock' not in d['availability'].lower():
                    notes.append(d['availability'][:40])
                report += (f'| **${d["price_per_oz"]:.4f}** | ${d["price"]:.2f} | {d["fl_oz"]:.0f} oz '
                           f'| [{d["title"][:70]}]({d["link"]}) | {d["seller_info"]} | {", ".join(notes)} |\n')
            report += '\n'
        else:
            report += f'## No deals at or below ${self.price_threshold:.2f}/fl oz\n\n'

        if self.results:
            best = sorted(self.results, key=lambda r: r['price_per_oz'])[:10]
            report += '## Best current prices\n\n'
            report += '| $/fl oz | Price | Size | Product | Offer |\n|---|---|---|---|---|\n'
            for r in best:
                flag = ' ⚠️' if r['unit_price_mismatch'] else ''
                size = f'{r["fl_oz"]:.0f} oz' + (' (est.)' if r['fl_oz_estimated'] else '')
                offer = r['offer_type'] + ('' if 'in stock' in r['availability'].lower() else f', {r["availability"][:30]}')
                report += (f'| ${r["price_per_oz"]:.4f}{flag} | ${r["price"]:.2f} | {size} '
                           f'| [{r["title"][:70]}]({r["link"]}) | {offer} |\n')
            report += ('\n⚠️ = Amazon\'s own unit price disagrees with the pack size parsed from the title. '
                       '(est.) = size estimated from Amazon\'s rounded unit price.\n')
        return report


def main():
    tracker = MonsterDealTracker()
    log('=' * 70)
    log('🔋 MONSTER ENERGY DEAL TRACKER')
    log(f'   threshold ${tracker.price_threshold:.3f}/fl oz, min {tracker.min_fl_oz:.0f} fl oz, '
        f'{tracker.max_pages} page(s) x {len(tracker.queries)} query(ies)')
    log('=' * 70)

    with Fetcher(use_browser=tracker.use_browser, debug_dir=tracker.debug_dir) as fetcher:
        tracker.search_amazon(fetcher)
        if tracker.results and tracker.verify:
            tracker.verify_deals(fetcher)

    if not tracker.results:
        log('\n⚠️  No listings could be priced. Amazon is probably blocking requests.')
        tracker.save_state([], ok=False)
        return 2

    tracker.save_history()
    deals = tracker.find_deals()
    new_deals = tracker.save_state(deals, ok=True)
    report = tracker.generate_report(deals, new_deals)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)

    log('\n' + '=' * 70)
    log(report)
    log('=' * 70)
    if deals:
        log(f'\n🚨 {len(deals)} deal(s) at or below ${tracker.price_threshold:.2f}/fl oz '
            f'({len(new_deals)} new since last run)')
    else:
        log('\n📊 No deals below threshold. Keep monitoring!')
    return 0


if __name__ == '__main__':
    sys.exit(main())
