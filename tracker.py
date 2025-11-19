import requests
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup

class MonsterDealTracker:
    def __init__(self):
        self.price_threshold = 0.12  # $/fl oz
        self.results = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
        }
    
    def check_amazon(self):
        """Check Amazon for Monster Energy deals"""
        # Amazon search URL for Monster Energy drinks
        url = "https://www.amazon.com/s?k=monster+energy+drink+24+pack"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find product listings
            products = soup.find_all('div', {'data-component-type': 's-search-result'})
            
            for product in products[:5]:  # Check top 5 results
                try:
                    # Extract title
                    title_elem = product.find('h2', class_='a-size-mini')
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    
                    # Extract price
                    price_elem = product.find('span', class_='a-price-whole')
                    if not price_elem:
                        continue
                    price = float(price_elem.get_text(strip=True).replace(',', '').replace('$', ''))
                    
                    # Extract fluid oz (usually in title)
                    fl_oz = self.extract_fluid_oz(title)
                    if not fl_oz:
                        continue
                    
                    price_per_oz = price / fl_oz
                    
                    # Get product link
                    link_elem = product.find('a', class_='a-link-normal')
                    link = "https://www.amazon.com" + link_elem['href'] if link_elem else url
                    
                    self.results.append({
                        'retailer': 'Amazon',
                        'title': title,
                        'price': price,
                        'fl_oz': fl_oz,
                        'price_per_oz': round(price_per_oz, 3),
                        'link': link,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"Error checking Amazon: {e}")
    
    def check_walmart(self):
        """Check Walmart for Monster Energy deals"""
        url = "https://www.walmart.com/search?q=monster+energy+drink+24+pack"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            # Walmart heavily uses JavaScript, simple scraping won't work well
            # This is a placeholder - would need Selenium or API
            print("Walmart check requires more advanced setup (Selenium/API)")
        except Exception as e:
            print(f"Error checking Walmart: {e}")
    
    def extract_fluid_oz(self, text):
        """Extract fluid ounces from product title"""
        import re
        # Look for patterns like "24 Pack, 16 Fl Oz" or "16oz"
        patterns = [
            r'(\d+)\s*pack.*?(\d+)\s*fl\s*oz',
            r'(\d+)\s*pack.*?(\d+)\s*oz',
            r'(\d+)x(\d+)\s*fl\s*oz',
        ]
        
        text_lower = text.lower()
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                pack_size = int(match.group(1))
                can_size = int(match.group(2))
                return pack_size * can_size
        return None
    
    def save_results(self, filename='price_history.json'):
        """Save results to JSON file"""
        # Load existing history
        history = []
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                history = json.load(f)
        
        # Append new results
        history.extend(self.results)
        
        # Save back
        with open(filename, 'w') as f:
            json.dump(history, f, indent=2)
    
    def find_deals(self):
        """Find deals below threshold"""
        deals = [r for r in self.results if r['price_per_oz'] <= self.price_threshold]
        return deals
    
    def generate_report(self):
        """Generate markdown report"""
        report = f"# Monster Energy Deal Report\n\n"
        report += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        report += f"**Price Threshold:** ${self.price_threshold}/fl oz\n\n"
        
        deals = self.find_deals()
        
        if deals:
            report += f"## 🎉 {len(deals)} Deal(s) Found!\n\n"
            for deal in deals:
                report += f"### {deal['title']}\n"
                report += f"- **Retailer:** {deal['retailer']}\n"
                report += f"- **Price:** ${deal['price']:.2f} ({deal['fl_oz']} fl oz)\n"
                report += f"- **Price per fl oz:** ${deal['price_per_oz']:.3f} ⭐\n"
                report += f"- **Link:** {deal['link']}\n\n"
        else:
            report += "## No deals found below threshold\n\n"
            if self.results:
                report += "### Best current prices:\n\n"
                sorted_results = sorted(self.results, key=lambda x: x['price_per_oz'])[:3]
                for result in sorted_results:
                    report += f"- {result['retailer']}: ${result['price_per_oz']:.3f}/fl oz - {result['title'][:60]}...\n"
        
        return report

def main():
    tracker = MonsterDealTracker()
    
    print("Checking for Monster Energy deals...")
    tracker.check_amazon()
    tracker.check_walmart()
    
    # Save results
    tracker.save_results()
    
    # Generate report
    report = tracker.generate_report()
    print(report)
    
    # Save report
    with open('deal_report.md', 'w') as f:
        f.write(report)

if __name__ == "__main__":
    main()