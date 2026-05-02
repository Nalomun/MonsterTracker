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
                    if asin and asin not in all_asins:
                        all_asins.add(asin)
                        self.parse_product(asin)
            
            except Exception as e:
                print(f"Error searching page {page}: {str(e)}")
        
        return self.results
    
    def parse_product(self, asin):
        """Parse a single product page"""
        url = f"https://www.amazon.com/dp/{asin}"
        
        try:
            time.sleep(2)  # Be polite to Amazon
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code != 200:
                print(f"  ASIN {asin}: Status {response.status_code}, skipping")
                return
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find product title
            title = soup.find('h1', {'id': 'title'}).text.strip()
            
            # Find price
            price = soup.find('span', {'id': 'priceblock_ourprice'}).text.strip()
            price = float(re.sub(r'[^\d\.]', '', price))
            
            # Find size
            size = soup.find('th', string='Item Weight').find_next('td').text.strip()
            size = re.sub(r'[^\d\.]', '', size)
            size = float(size)
            
            # Calculate price per fl oz
            price_per_oz = price / size
            
            # Check if price is below threshold
            if price_per_oz < self.price_threshold:
                self.results.append({
                    'asin': asin,
                    'title': title,
                    'price': price,
                    'size': size,
                    'price_per_oz': price_per_oz
                })
        
        except Exception as e:
            print(f"Error parsing ASIN {asin}: {str(e)}")