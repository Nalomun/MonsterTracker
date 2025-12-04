import requests
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup

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
        
        # Known Monster Energy products to check
        self.amazon_asins = [
            'B0BL7316GD',  # Monster Energy Ultra, Sugar Free, 16 Fl Oz (Pack of 24)
            'B01MZDN3TW',  # Monster Energy Drink, Green, Original, 16 Fl Oz (Pack of 24)
            'B094GZ4H4H',  # Monster Energy Zero Ultra, Sugar Free Energy Drink
            'B08GKYCLQT',  # Monster Energy Mega Monster
            'B0CLD3DXFT',  # Monster Energy Variety Pack
        ]
    
    def check_amazon_product(self, asin):
        """Check a specific Amazon product by ASIN"""
        url = f"https://www.amazon.com/dp/{asin}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code != 200:
                print(f"Failed to fetch {asin}: Status {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract title
            title = None
            title_elem = soup.find('span', {'id': 'productTitle'})
            if title_elem:
                title = title_elem.get_text(strip=True)
            
            if not title:
                print(f"Could not find title for {asin}")
                return None
            
            # Extract price - Amazon has multiple price formats
            price = None
            
            # Try whole price + fraction
            price_whole = soup.find('span', class_='a-price-whole')
            price_fraction = soup.find('span', class_='a-price-fraction')
            
            if price_whole:
                price_str = price_whole.get_text(strip=True).replace(',', '').replace('.', '')
                if price_fraction:
                    price_str += '.' + price_fraction.get_text(strip=True)
                try:
                    price = float(price_str)
                except:
                    pass
            
            # Alternative: try a-offscreen price
            if not price:
                price_elem = soup.find('span', class_='a-offscreen')
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
                    if price_match:
                        try:
                            price = float(price_match.group(1).replace(',', ''))
                        except:
                            pass
            
            if not price:
                print(f"Could not find price for {asin}: {title}")
                return None
            
            # Extract fluid oz from title and product details
            fl_oz = self.extract_fluid_oz_advanced(title, soup)
            
            if not fl_oz:
                print(f"Could not determine fluid oz for {asin}: {title}")
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
                'timestamp': datetime.now().isoformat()
            }
            
            print(f"✓ Found: {title[:50]}... - ${price:.2f} (${price_per_oz:.4f}/oz)")
            return result
            
        except Exception as e:
            print(f"Error checking Amazon ASIN {asin}: {e}")
            return None
    
    def check_amazon(self):
        """Check all Amazon products"""
        print("\n🔍 Checking Amazon products...")
        for asin in self.amazon_asins:
            result = self.check_amazon_product(asin)
            if result:
                self.results.append(result)
    
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
        
        # Patterns to match
        patterns = [
            # "24 Pack, 16 Fl Oz"
            r'(\d+)\s*pack[,\s]+(\d+\.?\d*)\s*fl\.?\s*oz',
            # "Pack of 24, 16 oz"
            r'pack\s+of\s+(\d+)[,\s]+(\d+\.?\d*)\s*oz',
            # "24 x 16 fl oz"
            r'(\d+)\s*x\s*(\d+\.?\d*)\s*fl\.?\s*oz',
            # "16 Fl Oz (Pack of 24)"
            r'(\d+\.?\d*)\s*fl\.?\s*oz\s*\(pack\s+of\s+(\d+)\)',
            # "(24 Count) 16 oz"
            r'\((\d+)\s*count\)[,\s]*(\d+\.?\d*)\s*oz',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    num1 = float(match.group(1))
                    num2 = float(match.group(2))
                    # Determine which is pack size vs can size
                    # Usually pack size is larger number
                    if num1 > num2:
                        return num1 * num2
                    else:
                        return num2 * num1
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
            report += f"## 🎉 {len(deals)} Deal(s) Found!\n\n"
            for deal in sorted(deals, key=lambda x: x['price_per_oz']):
                report += f"### {deal['title']}\n\n"
                report += f"- **Retailer:** {deal['retailer']}\n"
                report += f"- **Price:** ${deal['price']:.2f} ({deal['fl_oz']:.0f} fl oz total)\n"
                report += f"- **Price per fl oz:** ${deal['price_per_oz']:.4f} ⭐ **BELOW THRESHOLD**\n"
                report += f"- **Link:** [{deal['asin']}]({deal['link']})\n"
                report += f"- **Savings:** ${(self.price_threshold - deal['price_per_oz']) * deal['fl_oz']:.2f} vs threshold\n\n"
        else:
            report += "## ℹ️ No deals found below threshold\n\n"
            if self.results:
                report += f"Checked {len(self.results)} product(s). Best current prices:\n\n"
                sorted_results = sorted(self.results, key=lambda x: x['price_per_oz'])[:5]
                for result in sorted_results:
                    report += f"- **{result['retailer']}**: ${result['price_per_oz']:.4f}/fl oz\n"
                    report += f"  - {result['title'][:80]}...\n"
                    report += f"  - [View on Amazon]({result['link']})\n\n"
        
        return report

def main():
    tracker = MonsterDealTracker()
    
    print("=" * 60)
    print("🔋 MONSTER ENERGY DEAL TRACKER")
    print("=" * 60)
    
    tracker.check_amazon()
    
    if not tracker.results:
        print("\n⚠️  No results found. Amazon may be blocking requests.")
        print("Try running again or check your internet connection.")
        return
    
    # Save results
    tracker.save_results()
    
    # Generate report
    report = tracker.generate_report()
    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)
    
    # Save report
    with open('deal_report.md', 'w') as f:
        f.write(report)
    
    print(f"\n✅ Report saved to deal_reporta.md")
    
    # Print summary
    deals = tracker.find_deals()
    if deals:
        print(f"\n🚨 ALERT: {len(deals)} deal(s) below ${tracker.price_threshold}/oz threshold!")
    else:
        print(f"\n📊 No deals below threshold. Keep monitoring!")

if __name__ == "__main__":
    main()