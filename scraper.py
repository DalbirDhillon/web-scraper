import requests
from bs4 import BeautifulSoup
import csv
import time

BASE_URL = "https://quotes.toscrape.com/page/{}/"

def scrape_page(page_number):
    """Scrape a single page of quotes"""
    url = BASE_URL.format(page_number)
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # Handle bad responses
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    quotes = []

    for quote in soup.find_all("div", class_="quote"):
        text = quote.find("span", class_="text").get_text(strip=True)
        author = quote.find("small", class_="author").get_text(strip=True)
        tags = [tag.get_text(strip=True) for tag in quote.find_all("a", class_="tag")]

        quotes.append({
            "text": text,
            "author": author,
            "tags": ", ".join(tags)
        })
    return quotes

def scrape_all_pages():
    """Scrapes multiple pages until no more found"""
    page_number = 1
    all_quotes = []

    while True:
        print(f"Scraping page {page_number}...")
        quotes = scrape_page(page_number)
        if not quotes:  # No more pages or error
            break
        all_quotes.extend(quotes)
        page_number += 1
        time.sleep(1)  # Be polite (avoid hammering)

    return all_quotes

def save_to_csv(quotes, filename="output.csv"):
    """Save extracted quotes to CSV"""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "author", "tags"])
        writer.writeheader()
        writer.writerows(quotes)
    print(f"Data saved to {filename}")

if __name__ == "__main__":
    data = scrape_all_pages()
    save_to_csv(data)