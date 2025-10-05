

import os
import time
import re
from typing import List, Optional
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


BASE_URL = "https://www.finsmes.com/"  
SAVE_DIR = "articles"
DELAY_BETWEEN_REQUESTS = 2.0  
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0 
REQUEST_TIMEOUT = 15  


ARTICLE_LIMIT: Optional[int] = None


scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "mobile": False
    }
)

scraper.headers.update({
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://www.google.com",
})


os.makedirs(SAVE_DIR, exist_ok=True)



def safe_filename(s: str, max_len: int = 120) -> str:
    """
    Create a filesystem-safe filename from a string.
    """
    s = s.strip()
    # Replace spaces with underscores
    s = re.sub(r"\s+", "_", s)
    # Keep only safe characters
    s = re.sub(r"[^A-Za-z0-9_\-\.]", "", s)
    # Trim
    if len(s) > max_len:
        s = s[:max_len]
    return s or "article"


def save_article_to_txt(title: str, url: str, content: str) -> None:
   
    parsed = urlparse(url)
    slug = parsed.path.rstrip("/").split("/")[-1] or "article"
    base = f"{slug}_{title[:60]}".strip()
    filename = safe_filename(base) + ".txt"
    filepath = os.path.join(SAVE_DIR, filename)

    # Avoid overwrite: add numeric suffix
    count = 1
    while os.path.exists(filepath):
        filepath = os.path.join(SAVE_DIR, f"{safe_filename(base)}_{count}.txt")
        count += 1

    with open(filepath, "w", encoding="utf-8") as f:
        # write metadata then content
        f.write(f"Source: {url}\n")
        f.write(f"Title: {title}\n")
        f.write("=" * 80 + "\n\n")
        f.write(content)
    print(f"[SAVED] {os.path.basename(filepath)}")


def fetch_html(url: str, timeout: int = REQUEST_TIMEOUT, max_retries: int = MAX_RETRIES) -> Optional[str]:
    attempt = 0
    backoff = 1.0
    while attempt < max_retries:
        try:
            resp = scraper.get(url, timeout=timeout)
            resp.raise_for_status()
            # Basic content-type sanity check
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
                print(f"[WARN] Unexpected Content-Type for {url}: {ctype}")
            return resp.text
        except Exception as e:
            attempt += 1
            print(f"[ERROR] Fetch {url} failed (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                sleep_time = backoff * RETRY_BACKOFF
                print(f"[INFO] Retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)
                backoff *= RETRY_BACKOFF
            else:
                print(f"[ERROR] Giving up on {url}")
    return None

def extract_article_links(listing_html: str, base_url: str) -> List[str]:
    """
    Extract article links from the listing page.
    The selector is tuned to the structure you used earlier, but has fallbacks.
    """
    soup = BeautifulSoup(listing_html, "lxml")
    links: List[str] = []

    for h3 in soup.find_all("h3", class_="entry-title td-module-title"):
        a = h3.find("a", href=True)
        if a:
            links.append(urljoin(base_url, a["href"]))

    # Fallback #1: common article link pattern (article titles)
    if not links:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # simple heuristic for article links: same domain + path length > 1 and includes year or words
            if href.startswith(base_url) or urljoin(base_url, href).startswith(base_url):
                full = urljoin(base_url, href)
                # skip obvious non-article links (css/js/pdf anchors)
                if any(x in full.lower() for x in (".pdf", ".jpg", ".png", "#", "?replytocom")):
                    continue
                links.append(full)

    # Deduplicate preserving order
    seen = set()
    uniq_links = []
    for l in links:
        if l not in seen:
            seen.add(l)
            uniq_links.append(l)

    return uniq_links


from typing import Tuple

def extract_article_content(html: str) -> Tuple[str, str]:
    """
    Return (title, content_text). Use a few fallbacks for selectors.
    """
    soup = BeautifulSoup(html, "lxml")

    
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Look for common in-page title elements
    for sel in [
        ("h1", {}),
        ("h1", {"class": "entry-title"}),
        ("h1", {"class": "td-page-title"}),
        ("h1", {"class": "post-title"}),
    ]:
        tag = soup.find(sel[0], sel[1])
        if tag and tag.get_text(strip=True):
            title = tag.get_text(strip=True)
            break
    content_selectors = [
        ("div", {"class": "tdb-block-inner td-fix-index"}),  # your original
        ("div", {"class": "td-post-content"}),               # common td theme
        ("div", {"class": "entry-content"}),
        ("div", {"class": "post-content"}),
        ("article", {}),
    ]

    content_text = ""
    for name, attrs in content_selectors:
        node = soup.find(name, attrs=attrs)
        if node:
            # remove script/style
            for bad in node.find_all(["script", "style", "noscript", "iframe"]):
                bad.decompose()
            text = node.get_text(separator="\n", strip=True)
            if text and len(text) > 50:
                content_text = text
                break

    if not content_text:
        body = soup.body
        if body:
            candidates = []
            for div in body.find_all(["div", "section", "article"]):
                txt = div.get_text(separator="\n", strip=True)
                candidates.append((len(txt), txt))
            if candidates:
                candidates.sort(reverse=True)
                largest = candidates[0][1]
                if len(largest) > 100:
                    content_text = largest

    return title or "untitled", content_text or ""


def scrape_articles(base_url: str):
    print(f"[START] Scraping listing: {base_url}")
    listing_html = fetch_html(base_url)
    if not listing_html:
        print("[ERROR] Could not load the base listing page. Exiting.")
        return

    links = extract_article_links(listing_html, base_url)
    if ARTICLE_LIMIT:
        links = links[:ARTICLE_LIMIT]

    print(f"[INFO] Found {len(links)} candidate links.")

    for idx, link in enumerate(links, start=1):
        print(f"\n[{idx}/{len(links)}] Processing: {link}")
        # polite delay
        time.sleep(DELAY_BETWEEN_REQUESTS)

        article_html = fetch_html(link)
        if not article_html:
            print("[WARN] Skipping due to fetch failure.")
            continue

        title, content = extract_article_content(article_html)
        if not content.strip():
            print("[WARN] No content extracted for:", link)
            continue

        save_article_to_txt(title=title, url=link, content=content)

    print("\n[DONE] Scraping finished.")


if __name__ == "__main__":
    scrape_articles(BASE_URL)
