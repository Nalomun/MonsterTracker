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
                    
                    # Avoid duplicates
                    if asin in all_asins:
                        continue
                    all_asins.add(asin)
                    
                    # Extract title
                    title_elem = product.find('h2')
                    title = title_elem.get_text(strip=True) if title_elem else "Unknown Product"
                    
                    # Skip irrelevant results
                    if 'monster' not in title.lower() or 'energy' not in title.lower():
                        continue
                    
                    # Extract price
                    price = self.extract_price_from_product(product)
                    if price is None:
                        continue
                    
                    # Parse volume info from title
                    total_fl_oz, count, size_oz = self.parse_volume_from_title(title)
                    if total_fl_oz == 0:
                        continue
                    
                    # Calculate price per fl oz
                    price_per_oz = price / total_fl_oz
                    
                    # Check against threshold
                    if price_per_oz < self.price_threshold:
                        self.results.append({
                            'title': title,
                            'asin': asin,
                            'price': round(price, 2),
                            'total_fl_oz': total_fl_oz,
                            'count': count,
                            'size_oz': size_oz,
                            'price_per_oz': round(price_per_oz, 4),
                            'threshold': self.price_threshold,
                            'savings': round((self.price_threshold * total_fl_oz) - price, 2),
                            'link': f"https://www.amazon.com/dp/{asin}",
                            'retailer': 'Amazon',
                            'seller': 'Unknown'
                        })
                        
            except requests.RequestException as e:
                print(f"  Error fetching page {page}: {str(e)}")
                continue
            except Exception as e:
                print(f"  Unexpected error on page {page}: {str(e)}")
                continue
        
        print(f"✅ Found {len(self.results)} deal(s) below ${self.price_threshold}/fl oz")

    def extract_price_from_product(self, product):
        """Extract price from Amazon product card using multiple possible selectors"""
        try:
            # Try primary price format: <span class="a-price"><span class="a-offscreen">$X.XX</span></span>
            price_elem = product.find('span', class_='a-price')
            if price_elem:
                price_text = price_elem.find('span', class_='a-offscreen')
                if price_text:
                    price_str = price_text.get_text(strip=True)
                    return self.parse_price_string(price_str)

            # Fallback: find any $X.XX pattern in the block
            text = product.get_text(separator=' ', strip=True)
            price_match = re.search(r'\$\s*(\d+\.?\d*)', text)
            if price_match:
                return float(price_match.group(1))

            return None
        except:
            return None

    def parse_price_string(self, price_str):
        """Convert price string like '$29.99' to float"""
        try:
            return float(re.sub(r'[^\d.]', '', price_str))
        except:
            return None

    def parse_volume_from_title(self, title):
        """Parse pack count, size per can, and total fl oz from product title"""
        title_lower = title.lower()
        
        # Extract pack count (e.g., "pack of 24", "24 count", "24 pack")
        count_match = re.search(r'(?:pack of|count|pack|pck|pk)\s*(\d+)', title_lower, re.IGNORECASE)
        count = int(count_match.group(1)) if count_match else 1
        
        # Extract size per can in ounces (e.g., "16 ounce", "16 oz")
        size_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:fl\.?\s*oz|ounce|oz)', title_lower)
        size_oz = float(size_match.group(1)) if size_match else 0.0
        
        total_fl_oz = count * size_oz
        return round(total_fl_oz, 2), count, round(size_oz, 2)

    def generate_report(self):
        """Generate markdown-style deal report"""
        if not self.results:
            print("\n❌ No deals found below threshold.")
            return ""

        # Sort by best deal (lowest price per oz)
        sorted_results = sorted(self.results, key=lambda x: x['price_per_oz'])

        report_lines = [
            "# Monster Energy Deal Report",
            "",
            f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "",
            f"**Price Threshold:** ${self.price_threshold:.3f}/fl oz",
            "",
            f"## 🎉 {len(sorted_results)} Deal(s) Found Below ${self.price_threshold:.3f}/oz!",
            ""
        ]

        for deal in sorted_results:
            report_lines.extend([
                f"### {deal['title']}",
                "",
                f"- **Retailer:** {deal['retailer']}",
                f"- **Seller:** {deal['seller']}",
                f"- **Price:** ${deal['price']} ({deal['total_fl_oz']} fl oz total)",
                f"- **Price per fl oz:** ${deal['price_per_oz']:.4f} ⭐ **BELOW THRESHOLD**",
                f"- **Link:** [{deal['asin']}]({deal['link']})",
                f"- **Savings:** ${deal['savings']} vs threshold",
                ""
            ])

        report = "\n".join(report_lines)
        print("\n✅ Report generated.")
        return report

    def run(self):
        """Run full tracking workflow"""
        self.results.clear()
        self.search_amazon_monsters(max_pages=3)
        return self.generate_report()