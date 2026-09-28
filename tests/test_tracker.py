"""Unit tests for the parsing logic in tracker.py (no network access)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker import (  # noqa: E402
    MonsterDealTracker, extract_fluid_oz, looks_blocked, parse_money,
    parse_product_page, parse_search_cards,
)


def test_extract_fluid_oz_common_phrasings():
    cases = {
        'Monster Energy Drink, Green, Original, 16 Ounce (Pack of 24)': 384,
        'Monster Energy Zero Sugar, Low Calorie Energy Drink, 16 Ounce | Pack of 12': 192,
        'Monster Energy Ultra Sunrise, Sugar Free Energy Drink, 16 Fl Oz (Pack of 15)': 240,
        'Monster Energy Drink - Ultra Violet - 16fl.oz.(Pack of 16)': 256,
        'New 381907 Monster Ultra Paradise Energy Drink 16 Oz (24-Pack) Fruit Drink': 384,
        'Monster Energy 24 ounce cans with Resealable Lids (Mega Monster, 12 Cans)': 288,
        'Monster Energy Ultra Zero Sugar Energy Drinks 16 ounce cans (Variety Pack 1, 6 Cans)': 96,
        'Monster Energy, Original, 16 fl oz, 4 Pack': 64,
        'Monster Energy Drink 8 Pack, 24 Ounce Cans, Lo Carb Flavor': 192,
        'Monster Energy Drinks, Zero Ultra, 6 Pack, 72 Ounce': 72,
        'Monster Mix Energy Ultra Watermelon, 16 Fl Oz (Pack of 24) Net Wt 384 Fl Oz': 384,
        'Monster Energy Rehab LPWBT, Variety Pack, Energy Iced Tea, 15.5 Ounce | Pack of 15': 232.5,
        'Monster Zero Ultra - 16 Ounce - 24 Pack (Pack of 4)': 1536,
        'Monster Energy Ultra Fiesta & Ultra Rosa 16 ounce cans (2 Flavor Pack, 12 Cans)': 192,
        'Monster Energy Drink, Green Original, 10.5 Ounce (Pack of 12)': 126,
        'Monster Energy Ultra Strawberry Dreams, Sugar Free Energy Drink, 16oz': 16,
        'Monster Energy Zero Sugar, 16oz (Pack of 15) + Monster Lo-Carb, 16oz (Pack of 15) | Monster Energy Bundle (Pack of 30)': 480,
        'Monster Java (Coffe+Energy) 6 pack (6 pack, Java Variety) 15 fl oz': 90,
    }
    for title, expected in cases.items():
        assert extract_fluid_oz(title) == expected, title


def test_extract_fluid_oz_metric_and_missing():
    assert abs(extract_fluid_oz('Monster Energy Khaotic Punch, 473 mL Cans, 12 Pack') - 191.88) < 0.05
    assert abs(extract_fluid_oz('Monster Mariposa Drink, 500mL Cans, 24 Pack') - 405.84) < 0.05
    # Caffeine milligrams must not be mistaken for millilitres.
    assert abs(extract_fluid_oz('Monster Reserve, 175mg Caffeine, 473mL Cans, 12 Pack') - 191.88) < 0.05
    assert extract_fluid_oz('Monster Java 6 pack (6 pack, Java Variety)') is None
    assert extract_fluid_oz('') is None
    assert extract_fluid_oz(None) is None


def test_parse_money():
    assert parse_money('$1,234.56') == 1234.56
    assert parse_money('$21.49') == 21.49
    assert parse_money('') is None
    assert parse_money('no price') is None


def test_looks_blocked():
    assert looks_blocked('')
    assert looks_blocked('<html><title>Sorry! Something went wrong!</title></html>')
    real = '<html><head><title>Amazon.com : x</title></head><body>' + \
        '<div data-component-type="s-search-result"></div>' + 'x' * 30000 + '</body></html>'
    assert not looks_blocked(real)


CARD = '''
<div data-component-type="s-search-result" data-asin="{asin}">
  <div data-cy="title-recipe">
    <h2><span>Monster</span></h2>
    <a class="a-link-normal s-line-clamp-3 s-link-style a-text-normal" href="/dp/{asin}">
      <span>Energy Zero Sugar, 16 Ounce (Pack of 15), Can</span></a>
  </div>
  <img class="s-image" alt="Monster Energy Zero Sugar, 16 Ounce (Pack of 15), Can"/>
  {price}
  {secondary}
</div>
'''
PRICE = '''<div data-cy="price-recipe"><a class="a-link-normal">
  <span class="a-price" data-a-size="xl"><span class="a-offscreen">$21.49</span></span>
  <span>( <span class="a-price a-text-price" data-a-size="b"><span class="a-offscreen">$0.09</span></span>
  <span>$0.09/fluid ounce)</span></span>
  <span class="a-price a-text-price" data-a-size="b"><span class="a-offscreen">$26.98</span></span>
</a></div>'''
SECONDARY = '''<div data-cy="secondary-offer-recipe"><span>No featured offers available</span>
  <span class="a-color-base">$42.00</span><span>(10 new offers)</span></div>'''


def _page(*cards):
    return '<html><body>' + ''.join(cards) + '</body></html>'


def test_parse_search_cards_featured_offer():
    html = _page(CARD.format(asin='B0BL6X167P', price=PRICE, secondary=''))
    [card] = parse_search_cards(html)
    assert card['asin'] == 'B0BL6X167P'
    assert card['title'] == 'Monster Energy Zero Sugar, 16 Ounce (Pack of 15), Can'
    assert card['price'] == 21.49
    assert card['offer_type'] == 'featured'
    assert card['amazon_unit_price'] == 0.09
    assert card['amazon_unit'] == 'fluid ounce'
    assert not card['out_of_stock']
    assert not card['sponsored']


def test_parse_search_cards_third_party_only():
    html = _page(CARD.format(asin='B006IMBHVU', price='', secondary=SECONDARY))
    [card] = parse_search_cards(html)
    assert card['price'] == 42.0
    assert card['offer_type'] == 'third_party'
    assert card['other_offer_count'] == 10


def test_build_result_and_deals():
    t = MonsterDealTracker()
    t.price_threshold = 0.12
    t.min_fl_oz = 64
    html = _page(CARD.format(asin='B0BL6X167P', price=PRICE, secondary=''))
    [card] = parse_search_cards(html)
    r = t.build_result(card)
    assert r['fl_oz'] == 240
    assert r['price_per_oz'] == round(21.49 / 240, 4)
    assert not r['unit_price_mismatch']
    t.results.append(r)
    assert t.find_deals() == [r]

    # Non-Monster listings and small packs are ignored.
    card['title'] = 'GHOST Energy Drink, 16 Ounce (Pack of 15)'
    assert t.build_result(card) is None
    card['title'] = 'Monster Energy, 16 Ounce (Pack of 2)'
    card['amazon_unit_price'] = None
    assert t.build_result(card) is None


def test_build_result_uses_variant_text_when_title_is_truncated():
    t = MonsterDealTracker()
    card = {'asin': 'X', 'title': 'Monster Energy Zero Ultra, Sugar Free Energy Drink, 16 Ounce',
            'variant': 'Pack of 15', 'price': 26.98, 'offer_type': 'featured',
            'amazon_unit_price': 0.11, 'amazon_unit': 'fluid ounce', 'other_offer_price': None,
            'other_offer_count': None, 'out_of_stock': False, 'sponsored': False}
    r = t.build_result(card)
    assert r['fl_oz'] == 240
    assert r['fl_oz_source'] == 'title+variant'
    assert not r['fl_oz_estimated']
    assert r['title'].endswith('(Pack of 15)')


def test_estimated_size_near_threshold_is_not_a_deal():
    t = MonsterDealTracker()
    t.price_threshold = 0.12
    card = {'asin': 'X', 'title': 'Monster Energy Ultra Violet, 16 Ounce', 'variant': '', 'price': 29.98,
            'offer_type': 'featured', 'amazon_unit_price': 0.12, 'amazon_unit': 'fluid ounce',
            'other_offer_price': None, 'other_offer_count': None, 'out_of_stock': False, 'sponsored': False}
    r = t.build_result(card)
    assert r['fl_oz_estimated']
    t.results.append(r)
    assert t.find_deals() == []          # really $0.1249/oz for a 15-pack
    assert t.find_deals(include_unverified=True) == [r]  # still gets verified
    card['amazon_unit_price'] = 0.09
    r2 = t.build_result(card)
    t.results = [r2]
    assert t.find_deals() == [r2]        # clearly below even with rounding


def test_build_result_uses_amazon_unit_price_when_title_lacks_count():
    t = MonsterDealTracker()
    card = {'asin': 'X', 'title': 'Monster Energy - Ultra Watermelon - 16 ounce', 'variant': '', 'price': 32.30,
            'offer_type': 'featured', 'amazon_unit_price': 0.17, 'amazon_unit': 'ounce',
            'other_offer_price': None, 'other_offer_count': None, 'out_of_stock': False, 'sponsored': False}
    r = t.build_result(card)
    assert r['fl_oz_source'] == 'amazon_unit_price'
    assert r['fl_oz'] == 190.0


def test_mismatch_flag_excludes_from_deals():
    t = MonsterDealTracker()
    t.price_threshold = 0.12
    card = {'asin': 'X', 'title': 'Monster Energy Zero Sugar, 16 Ounce (Pack of 12)', 'variant': '', 'price': 21.58,
            'offer_type': 'featured', 'amazon_unit_price': 1.35, 'amazon_unit': 'fluid ounce',
            'other_offer_price': None, 'other_offer_count': None, 'out_of_stock': False, 'sponsored': False}
    r = t.build_result(card)
    assert r['unit_price_mismatch']
    t.results.append(r)
    assert t.find_deals() == []
    assert t.find_deals(include_unverified=True) == [r]


PRODUCT = '''<html><head><title>x</title></head><body>
<span id="productTitle"> Monster Energy Zero Sugar, 16 Ounce (Pack of 15) </span>
<div id="corePrice_feature_div"><span class="a-price"><span class="a-offscreen">$21.49</span></span>
  <span>$0.09 per fluid ounce</span></div>
<div id="snsAccordionRowMiddle"><span class="a-price"><span class="a-offscreen">$20.42</span></span></div>
<div id="availability"><span>In Stock</span></div>
<div id="merchantInfoFeature_feature_div"><span class="offer-display-feature-text-message">Amazon.com</span></div>
</body></html>'''


def test_parse_product_page():
    info = parse_product_page(PRODUCT)
    assert info['title'].startswith('Monster Energy Zero Sugar')
    assert info['price'] == 21.49
    assert info['sns_price'] == 20.42
    assert info['availability'] == 'In Stock'
    assert info['seller'] == 'Amazon.com'
    assert info['amazon_unit_price'] == 0.09


def test_save_state_detects_new_deals(tmp_path):
    t = MonsterDealTracker()
    state = tmp_path / 'state.json'
    deal = {'asin': 'A', 'price_per_oz': 0.10, 'title': 't'}
    assert t.save_state([deal], ok=True, filename=str(state)) == ['A']
    assert t.save_state([deal], ok=True, filename=str(state)) == []
    cheaper = dict(deal, price_per_oz=0.09)
    assert t.save_state([cheaper], ok=True, filename=str(state)) == ['A']
    assert t.save_state([cheaper, {'asin': 'B', 'price_per_oz': 0.11, 'title': 'u'}],
                        ok=True, filename=str(state)) == ['B']
