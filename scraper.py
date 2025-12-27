import time
import logging
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ----------------------------
# Config
# ----------------------------
BASE_URL = "https://quotes.toscrape.com/"
START_PATH = "page/1/"
OUTPUT_EXCEL = "quotes_analysis.xlsx"
PLOTS_DIR = "plots"
REQUEST_TIMEOUT = 8
SLEEP_BETWEEN_PAGES = 1.0
FETCH_AUTHOR_METADATA = True  # grabs author born date/location/description
USER_AGENT = "Mozilla/5.0 (compatible; OutlierPlaygroundBot/1.0; +https://outlier.ai/)"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# ----------------------------
# HTTP session with retries
# ----------------------------
def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    retry = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

SESSION = make_session()

# ----------------------------
# Helpers
# ----------------------------
def get_soup(url: str) -> BeautifulSoup | None:
    try:
        r = SESSION.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP error for {url}: {e}")
        return None

def safe_text(node, default=""):
    try:
        return node.get_text(strip=True) if node else default
    except Exception:
        return default

def parse_author_page(author_url: str) -> dict:
    """Parse author metadata (born date/location/description). Robust to missing fields."""
    soup = get_soup(author_url)
    if not soup:
        return {}

    try:
        name = safe_text(soup.find("h3", class_="author-title"))
        born_date = safe_text(soup.find("span", class_="author-born-date"))
        born_location = safe_text(soup.find("span", class_="author-born-location"))
        description = safe_text(soup.find("div", class_="author-description"))
        return {
            "author_name_page": name,
            "author_born_date": born_date,
            "author_born_location": born_location,
            "author_description": description
        }
    except Exception as e:
        logging.warning(f"Parsing error on author page {author_url}: {e}")
        return {}

def scrape_quotes_site(start_url: str) -> list[dict]:
    """
    Crawl pages and extract structured data:
    - title/text (quote)
    - links (page_url, author_url)
    - metadata (tags, author bio fields)
    Includes robust handling for HTTP + parsing issues.
    """
    all_rows = []
    author_cache = {}

    next_url = start_url
    page_number = 1

    while next_url:
        logging.info(f"Scraping page {page_number}: {next_url}")
        soup = get_soup(next_url)
        if not soup:
            # Stop on persistent failure (or you can continue)
            break

        quote_blocks = soup.find_all("div", class_="quote")
        if not quote_blocks:
            logging.info("No quotes found; stopping.")
            break

        for qb in quote_blocks:
            try:
                quote_text = safe_text(qb.find("span", class_="text"))
                author = safe_text(qb.find("small", class_="author"))
                tags = [safe_text(t) for t in qb.find_all("a", class_="tag")]

                about_link = qb.find("a", string="(about)")
                author_url = urljoin(BASE_URL, about_link["href"]) if about_link and about_link.get("href") else ""

                row = {
                    "source": "quotes.toscrape.com",
                    "page_number": page_number,
                    "page_url": next_url,
                    "title_or_text": quote_text,
                    "author": author,
                    "author_url": author_url,
                    "tags": ", ".join([t for t in tags if t]),
                    "scraped_at_utc": datetime.utcnow().isoformat(timespec="seconds")
                }

                if FETCH_AUTHOR_METADATA and author_url:
                    if author_url not in author_cache:
                        author_cache[author_url] = parse_author_page(author_url)
                    row.update(author_cache[author_url])

                all_rows.append(row)

            except Exception as e:
                logging.warning(f"Parsing error on page {next_url}: {e}")
                continue

        # Find next page link
        next_link = soup.select_one("li.next > a")
        if next_link and next_link.get("href"):
            next_url = urljoin(BASE_URL, next_link["href"])
            page_number += 1
            time.sleep(SLEEP_BETWEEN_PAGES)
        else:
            next_url = None

    return all_rows

# ----------------------------
# Analysis + Export (Pandas/Excel/Matplotlib)
# ----------------------------
def analyze_and_export(rows: list[dict], output_excel: str = OUTPUT_EXCEL):
    if not rows:
        logging.warning("No data collected. Nothing to export.")
        return

    df = pd.DataFrame(rows)

    # Basic cleaning/transforms
    df["tags_list"] = df["tags"].fillna("").apply(
        lambda s: [t.strip() for t in s.split(",") if t.strip()]
    )

    # Summary tables
    quotes_per_author = (
        df.groupby("author", dropna=False)
          .size()
          .sort_values(ascending=False)
          .rename("quote_count")
          .reset_index()
    )

    exploded_tags = df.explode("tags_list")
    tag_counts = (
        exploded_tags[exploded_tags["tags_list"].notna() & (exploded_tags["tags_list"] != "")]
        .groupby("tags_list")
        .size()
        .sort_values(ascending=False)
        .rename("tag_count")
        .reset_index()
        .rename(columns={"tags_list": "tag"})
    )

    # Plots
    import os
    os.makedirs(PLOTS_DIR, exist_ok=True)

    top_authors = quotes_per_author.head(10)
    plt.figure(figsize=(10, 5))
    plt.bar(top_authors["author"], top_authors["quote_count"])
    plt.xticks(rotation=45, ha="right")
    plt.title("Top 10 Authors by Quote Count")
    plt.tight_layout()
    authors_plot_path = os.path.join(PLOTS_DIR, "top_authors.png")
    plt.savefig(authors_plot_path, dpi=200)
    plt.close()

    top_tags = tag_counts.head(10)
    plt.figure(figsize=(10, 5))
    plt.bar(top_tags["tag"], top_tags["tag_count"])
    plt.xticks(rotation=45, ha="right")
    plt.title("Top 10 Tags")
    plt.tight_layout()
    tags_plot_path = os.path.join(PLOTS_DIR, "top_tags.png")
    plt.savefig(tags_plot_path, dpi=200)
    plt.close()

    # Excel export (raw + summaries)
    with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
        df.drop(columns=["tags_list"], errors="ignore").to_excel(writer, index=False, sheet_name="raw_quotes")
        quotes_per_author.to_excel(writer, index=False, sheet_name="summary_authors")
        tag_counts.to_excel(writer, index=False, sheet_name="summary_tags")

    logging.info(f"Saved Excel: {output_excel}")
    logging.info(f"Saved plots: {authors_plot_path}, {tags_plot_path}")

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    start_url = urljoin(BASE_URL, START_PATH)

    rows = scrape_quotes_site(start_url)
    analyze_and_export(rows, OUTPUT_EXCEL)