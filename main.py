from tracker import MonsterDealTracker

def main():
    tracker = MonsterDealTracker()
    results = tracker.search_amazon_monsters()
    
    if results:
        print("\n🎉 Deals found:")
        for result in results:
            print(f"  ASIN: {result['asin']}")
            print(f"  Title: {result['title']}")
            print(f"  Price: ${result['price']:.2f}")
            print(f"  Size: {result['size']} fl oz")
            print(f"  Price per fl oz: ${result['price_per_oz']:.4f}")
            print()
    else:
        print("\nNo deals found.")

if __name__ == "__main__":
    main()