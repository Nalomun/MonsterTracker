import requests
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
import time

class MonsterDealTracker:
    def __init__(self):
        self.price_threshold = 0.12  # $/fl oz
        self.results = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    def search_amazon_monsters(self, max_pages=3):
        """Search Amazon for Monster Energy drinks and extract all products"""
        print("\n🔍 Searching Amazon for Monster Energy drinks...")
        
        all_asins = set()
        
        for page in range(1, max_pages + 1):
            url = f"https://www.amazon.com/s?k=monster+energy+drink&page={page}"
            
            try:
                time.sleep(2)  # Be polite to Amazon
                response = requests.get(url, headers=self.headers, timeout=15)
                
                if response.status_code != 200:
                    print(f"  Page {page}: Status {response.status_code}, skipping")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find all product cards
                products = soup.find_all('div', {'data-component-type': 's-search-result'})
                
                if not products:
                    print(f"  Page {page}: No products found (Amazon may have changed layout)")
                    continue

                for product in products:
                    asin = product.get('data-asin')
                    if not asin:
                        continue

                    # Skip already seen ASINs
                    if asin in all_asins:
                        continue
                    all_asins.add(asin)

                    title_elem = product.find('h2')
                    price_whole = product.find('span', {'class': 'a-price-whole'})
                    price_fraction = product.find('span', {'class': 'a-price-fraction'})

                    if not title_elem or not price_whole or not price_fraction:
                        continue

                    title = title_elem.get_text(strip=True)
                    if 'monster' not in title.lower():
                        continue

                    try:
                        price = float(price_whole.get_text(strip=True).replace(',', '')) + \
                                float(price_fraction.get_text(strip=True)) / 100
                    except ValueError:
                        continue

                    # Extract pack size and can count using regex
                    pack_info = self.extract_pack_info(title)
                    if not pack_info:
                        continue

                    can_size_oz, count = pack_info
                    total_fl_oz = can_size_oz * count

                    if total_fl_oz <= 0:
                        continue

                    price_per_oz = price / total_fl_oz

                    if price_per_oz < self.price_threshold:
                        self.results.append({
                            'title': title,
                            'asin': asin,
                            'price': round(price, 2),
                            'total_fl_oz': total_fl_oz,
                            'price_per_oz': round(price_per_oz, 4),
                            'savings_vs_threshold': round((self.price_threshold - price_per_oz) * total_fl_oz, 2),
                            'link': f"https://www.amazon.com/dp/{asin}"
                        })

            except requests.exceptions.Timeout:
                print(f"  Page {page}: Request timed out, skipping")
                continue
            except requests.exceptions.RequestException as e:
                print(f"  Page {page}: Request error: {e}, skipping")
                continue
            except Exception as e:
                print(f"  Page {page}: Unexpected error: {e}, skipping")
                continue

        print(f"✅ Found {len(self.results)} deal(s) under ${self.price_threshold}/fl oz")

    def extract_pack_info(self, title):
        """Extract can size in oz and pack count from product title"""
        title_lower = title.lower()

        # Extract can size (e.g., 16 oz, 15.5 oz)
        oz_match = re.search(r'(\d+(?:\.\d+)?)\s*fl\s*oz|(\d+(?:\.\d+)?)\s*oz', title_lower)
        if not oz_match:
            return None
        can_size_oz = float(oz_match.group(1) or oz_match.group(2))

        # Extract pack count (e.g., Pack of 24, 24-Pack, 24 Count)
        count_match = re.search(r'(pack of|pack-of|count|each|ea|/)\s*(\d+)', title_lower)
        if count_match:
            count = int(count_match.group(2))
        else:
            # Default to single can if no pack info
            count = 1

        return can_size_oz, count

    def generate_report(self):
        """Generate a markdown-style report of deals found"""
        if not self.results:
            print("\n❌ No deals found below threshold.")
            return

        print("\n🎉 DEALS FOUND BELOW THRESHOLD:")
        for deal in self.results:
            print(f"\n### {deal['title']}")
            print(f"- **Retailer:** Amazon")
            print(f"- **Seller:** Unknown")
            print(f"- **Price:** ${deal['price']} ({deal['total_fl_oz']} fl oz total)")
            print(f"- **Price per fl oz:** ${deal['price_per_oz']:.4f} ⭐ **BELOW THRESHOLD**")
            print(f"- **Link:** [{deal['asin']}]({deal['link']})")
            print(f"- **Savings:** ${deal['savings_vs_threshold']} vs threshold")

    def run(self):
        """Run the full tracking process"""
        self.results = []
        self.search_amazon_monsters(max_pages=3)
        self.generate_report()
        return self.results


# Run the tracker if executed directly
if __name__ == "__main__":
    tracker = MonsterDealTracker()
    tracker.run()