# govdeals_scraper.py

import requests
from bs4 import BeautifulSoup
import json

def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

def scrape_govdeals():
    config = load_config()
    url = "https://www.govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew&category=13"  # Trucks category
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    listings = soup.find_all("div", class_="auctionListing")
    results = []

    for listing in listings:
        title_tag = listing.find("div", class_="auctionTitle")
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        link_tag = listing.find("a")
        link = "https://www.govdeals.com" + link_tag["href"] if link_tag else "N/A"
        raw_text = listing.get_text().lower()

        # Model match
        if not any(model.lower() in raw_text for model in config["models"]):
            continue

        # Engine and specialty match
        engine_match = any(word in raw_text for word in config["engine_keywords"])
        special_match = any(word in raw_text for word in config["specialty_keywords"])

        # Try extracting price
        price = 0
        try:
            price_str = listing.find("span", class_="currency").get_text(strip=True).replace("$", "").replace(",", "")
            price = float(price_str)
        except:
            pass

        if price > config["max_bid"]:
            continue

        results.append({
            "title": title,
            "price": price,
            "engine_match": engine_match,
            "specialty_match": special_match,
            "link": link
        })

    return results

if __name__ == "__main__":
    trucks = scrape_govdeals()
    for truck in trucks:
        print(truck)
