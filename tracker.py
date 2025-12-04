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
                    break
                
                page_asins = 0
                for product in products:
                    # Extract ASIN from data-asin attribute
                    asin = product.get('data-asin')
                    if asin and asin not in all_asins:
                        all_asins.add(asin)
                        page_asins += 1
                
                print(f"  Page {page}: Found {page_asins} products")
                
            except Exception as e:
                print(f"  Page {page}: Error - {e}")
                break
        
        print(f"\n📦 Total unique products found: {len(all_asins)}")
        return list(all_asins)
    
    def check_amazon_product(self, asin):
        """Check a specific Amazon product by ASIN"""
        url = f"https://www.amazon.com/dp/{asin}"
        
        try:
            time.sleep(1)  # Rate limiting
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract title
            title = None
            title_elem = soup.find('span', {'id': 'productTitle'})
            if title_elem:
                title = title_elem.get_text(strip=True)
            
            if not title:
                return None
            
            # Skip non-Monster products (sometimes search returns related items)
            if 'monster' not in title.lower():
                return None
            
            # Extract price - check multiple sources to find the CHEAPEST option
            price = None
            seller_info = None
            prices_found = []
            
            # Method 1: Main buy box price
            buy_box_section = soup.find('div', {'id': 'apex_desktop'})
            if buy_box_section:
                price_whole = buy_box_section.find('span', class_='a-price-whole')
                price_fraction = buy_box_section.find('span', class_='a-price-fraction')
                
                if price_whole:
                    price_str = price_whole.get_text(strip=True).replace(',', '').replace('.', '')
                    if price_fraction:
                        price_str += '.' + price_fraction.get_text(strip=True)
                    try:
                        buybox_price = float(price_str)
                        prices_found.append(('Buy Box', buybox_price, 'Main listing'))
                    except:
                        pass
            
            # Method 2: Check "Other Sellers" section for cheaper alternatives
            other_sellers = soup.find('div', {'id': 'aod-offer-list'})
            if other_sellers:
                offers = other_sellers.find_all('div', {'id': re.compile(r'aod-offer-')})
                for offer in offers[:10]:  # Check up to 10 offers
                    try:
                        offer_price_elem = offer.find('span', class_='a-offscreen')
                        if offer_price_elem:
                            offer_price_text = offer_price_elem.get_text(strip=True)
                            offer_price_match = re.search(r'\$?([\d,]+\.?\d*)', offer_price_text)
                            if offer_price_match:
                                offer_price = float(offer_price_match.group(1).replace(',', ''))
                                
                                # Try to get seller name
                                seller_name_elem = offer.find('div', {'id': re.compile(r'aod-offer-soldBy-')})
                                seller_name = seller_name_elem.get_text(strip=True) if seller_name_elem else 'Third-party'
                                
                                prices_found.append(('Other Seller', offer_price, seller_name))
                    except:
                        continue
            
            # Method 3: Offscreen price (backup)
            if not prices_found:
                price_elem = soup.find('span', class_='a-offscreen')
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
                    if price_match:
                        try:
                            fallback_price = float(price_match.group(1).replace(',', ''))
                            prices_found.append(('Offscreen', fallback_price, 'Unknown'))
                        except:
                            pass
            
            # Choose the CHEAPEST price found
            if prices_found:
                prices_found.sort(key=lambda x: x[1])  # Sort by price
                price_source, price, seller_info = prices_found[0]
            
            if not price:
                return None
            
            # Extract fluid oz from title and product details
            fl_oz = self.extract_fluid_oz_advanced(title, soup)
            
            if not fl_oz:
                return None
            
            # Skip if unreasonably small (single cans, etc.) - focus on bulk deals
            if fl_oz < 64:  # Less than 4 cans worth
                return None
            
            price_per_oz = price / fl_oz
            
            result = {
                'retailer': 'Amazon',
                'asin': asin,
                'title': title,
                'price': price,
                'fl_oz': fl_oz,
                'price_per_oz': round(price_per_oz, 4),
                'link': f"https://www.amazon.com/dp/{asin}",
                'seller_info': seller_info if seller_info else 'Amazon/Unknown',
                'timestamp': datetime.now().isoformat()
            }
            
            # Show what we found
            status = "⭐ DEAL" if price_per_oz <= self.price_threshold else "  "
            print(f"  {status} ${price_per_oz:.4f}/oz - {title[:60]}...")
            
            return result
            
        except Exception as e:
            return None
    
    def check_amazon(self):
        """Search Amazon and check all Monster Energy products"""
        # First, search to get ASINs
        asins = self.search_amazon_monsters(max_pages=3)
        
        if not asins:
            print("⚠️  No products found in search")
            return
        
        print(f"\n🔎 Checking prices for {len(asins)} products...")
        print("=" * 70)
        
        checked = 0
        for asin in asins:
            result = self.check_amazon_product(asin)
            if result:
                self.results.append(result)
                checked += 1
            
            # Limit to avoid excessive requests
            if checked >= 20:
                print(f"\n  (Limited to first 20 valid products to avoid rate limiting)")
                break
        
        print("=" * 70)
        print(f"✓ Successfully checked {len(self.results)} products")
    
    def extract_fluid_oz_advanced(self, title, soup):
        """Extract fluid ounces from title and product details"""
        # First try title
        fl_oz = self.extract_fluid_oz(title)
        if fl_oz:
            return fl_oz
        
        # Try product details table
        try:
            details = soup.find('div', {'id': 'detailBullets_feature_div'})
            if details:
                text = details.get_text()
                fl_oz = self.extract_fluid_oz(text)
                if fl_oz:
                    return fl_oz
            
            # Try technical details
            tech_details = soup.find('table', {'id': 'productDetails_techSpec_section_1'})
            if tech_details:
                text = tech_details.get_text()
                fl_oz = self.extract_fluid_oz(text)
                if fl_oz:
                    return fl_oz
        except:
            pass
        
        return None
    
    def extract_fluid_oz(self, text):
        """Extract fluid ounces from text"""
        if not text:
            return None
            
        text_lower = text.lower()
        
        # Patterns to match (order matters - most specific first)
        patterns = [
            # "16 Ounce (Pack of 15)"
            r'(\d+\.?\d*)\s*ounce\s*\(pack\s+of\s+(\d+)\)',
            # "16 Fl Oz (Pack of 24)"
            r'(\d+\.?\d*)\s*fl\.?\s*oz\.?\s*\(pack\s+of\s+(\d+)\)',
            # "24 Pack, 16 Fl Oz"
            r'(\d+)\s*pack[,\s]+(\d+\.?\d*)\s*fl\.?\s*oz',
            # "Pack of 24, 16 oz"
            r'pack\s+of\s+(\d+)[,\s]+(\d+\.?\d*)\s*(?:fl\.?\s*)?oz',
            # "24 x 16 fl oz"
            r'(\d+)\s*x\s*(\d+\.?\d*)\s*fl\.?\s*oz',
            # "(24 Count) 16 oz"
            r'\((\d+)\s*count\)[,\s]*(\d+\.?\d*)\s*(?:fl\.?\s*)?oz',
            # "24-Pack 16 oz"
            r'(\d+)-pack\s+(\d+\.?\d*)\s*oz',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    num1 = float(match.group(1))
                    num2 = float(match.group(2))
                    # Calculate total fluid oz
                    total = num1 * num2
                    return total
                except:
                    continue
        
        return None
    
    def save_results(self, filename='price_history.json'):
        """Save results to JSON file"""
        history = []
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                try:
                    history = json.load(f)
                except:
                    history = []
        
        history.extend(self.results)
        
        with open(filename, 'w') as f:
            json.dump(history, f, indent=2)
        
        print(f"\n💾 Saved {len(self.results)} results to {filename}")
    
    def find_deals(self):
        """Find deals below threshold"""
        deals = [r for r in self.results if r['price_per_oz'] <= self.price_threshold]
        return deals
    
    def generate_report(self):
        """Generate markdown report"""
        report = f"# Monster Energy Deal Report\n\n"
        report += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        report += f"**Price Threshold:** ${self.price_threshold:.3f}/fl oz\n\n"
        
        deals = self.find_deals()
        
        if deals:
            report += f"## 🎉 {len(deals)} Deal(s) Found Below ${self.price_threshold}/oz!\n\n"
            for deal in sorted(deals, key=lambda x: x['price_per_oz']):
                report += f"### {deal['title']}\n\n"
                report += f"- **Retailer:** {deal['retailer']}\n"
                report += f"- **Seller:** {deal.get('seller_info', 'Unknown')}\n"
                report += f"- **Price:** ${deal['price']:.2f} ({deal['fl_oz']:.0f} fl oz total)\n"
                report += f"- **Price per fl oz:** ${deal['price_per_oz']:.4f} ⭐ **BELOW THRESHOLD**\n"
                report += f"- **Link:** [{deal['asin']}]({deal['link']})\n"
                report += f"- **Savings:** ${(self.price_threshold - deal['price_per_oz']) * deal['fl_oz']:.2f} vs threshold\n\n"
        else:
            report += "## ℹ️ No deals found below threshold\n\n"
            if self.results:
                report += f"Checked {len(self.results)} product(s). Best current prices:\n\n"
                sorted_results = sorted(self.results, key=lambda x: x['price_per_oz'])[:5]
                for i, result in enumerate(sorted_results, 1):
                    report += f"**#{i}. ${result['price_per_oz']:.4f}/fl oz** - {result['title'][:80]}\n"
                    report += f"   - ${result['price']:.2f} for {result['fl_oz']:.0f} fl oz\n"
                    report += f"   - [View on Amazon]({result['link']})\n\n"
        
        return report

def main():
    tracker = MonsterDealTracker()
    
    print("=" * 70)
    print("🔋 MONSTER ENERGY DEAL TRACKER")
    print("=" * 70)
    
    tracker.check_amazon()
    
    if not tracker.results:
        print("\n⚠️  No results found. Amazon may be blocking requests.")
        print("Try running again later or check your internet connection.")
        return
    
    # Save results
    tracker.save_results()
    
    # Generate report
    report = tracker.generate_report()
    print("\n" + "=" * 70)
    print(report)
    print("=" * 70)
    
    # Save report
    with open('deal_report.md', 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ Report saved to deal_report.md")
    
    # Print summary
    deals = tracker.find_deals()
    if deals:
        print(f"\n🚨 ALERT: {len(deals)} deal(s) below ${tracker.price_threshold}/oz threshold!")
        for deal in deals:
            print(f"   • ${deal['price_per_oz']:.4f}/oz - {deal['title'][:50]}...")
    else:
        print(f"\n📊 No deals below threshold. Keep monitoring!")

if __name__ == "__main__":
    main()