import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
from selectolax.lexbor import LexborHTMLParser

BASE_URL = "https://publicapis.dev"
OUTPUT_FILE = "APIs.json"
MAX_WORKERS = 20

def fetch_sitemap_urls():
    """Attempts to fetch all resource URLs from the sitemap."""
    print("[*] Fetching sitemap.xml...")
    try:
        r = requests.get(f"{BASE_URL}/sitemap.xml", impersonate="chrome", timeout=20)
        if r.status_code == 200:
            urls = re.findall(r"<loc>(.*?)</loc>", r.text)
            resources = [u for u in urls if "/resource/" in u]
            if resources:
                print(f"[+] Found {len(resources)} URLs in sitemap.")
                return resources
    except Exception as e:
        print(f"[!] Sitemap failed: {e}")
    return []

def parse_homepage_for_urls():
    """Fallback: Parse the homepage for resource links."""
    print("[*] Sitemap empty. Parsing homepage for links...")
    try:
        r = requests.get(BASE_URL, impersonate="chrome", timeout=20)
        if r.status_code == 200:
            tree = LexborHTMLParser(r.text)
            urls = set()
            for a in tree.css("a[href*='/resource/']"):
                href = a.attributes.get("href")
                if href:
                    full = BASE_URL + href if href.startswith("/") else href
                    urls.add(full)
            print(f"[+] Found {len(urls)} URLs on homepage.")
            return list(urls)
    except Exception as e:
        print(f"[!] Homepage failed: {e}")
    return []

def scrape_api_details(url):
    """Scrapes a single resource page for details."""
    try:
        r = requests.get(url, impersonate="chrome", timeout=20)
        if r.status_code != 200:
            return None
        
        tree = LexborHTMLParser(r.text)
        
        # 1. Extract Name
        name_node = tree.css_first("h1")
        name = name_node.text(strip=True) if name_node else ""
        
        # 2. Extract Category
        cat_node = tree.css_first(".category, .tag, .breadcrumb")
        category = cat_node.text(strip=True) if cat_node else ""
        
        # 3. Extract Description
        desc_node = tree.css_first("meta[name='description']")
        description = desc_node.attributes.get("content", "") if desc_node else ""
        
        # 4. Extract Actual API URL (first external link not pointing to publicapis.dev)
        api_url = ""
        for a in tree.css("a"):
            href = a.attributes.get("href", "")
            if href.startswith("http") and "publicapis.dev" not in href:
                api_url = href
                break
        
        return {
            "name": name,
            "category": category,
            "description": description,
            "api_url": api_url,
            "source_url": url
        }
    except Exception as e:
        print(f"[!] Error scraping {url}: {e}")
        return None

def main():
    # 1. Get all URLs
    urls = fetch_sitemap_urls()
    if not urls:
        urls = parse_homepage_for_urls()
    
    if not urls:
        print("[!] No URLs found. Exiting.")
        return
    
    # 2. Scrape pages in parallel
    print(f"[*] Scraping {len(urls)} API pages with {MAX_WORKERS} threads...")
    apis = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(scrape_api_details, url): url for url in urls}
        for i, future in enumerate(as_completed(future_to_url)):
            res = future.result()
            if res:
                apis.append(res)
            if (i + 1) % 100 == 0:
                print(f"    -> Scraped {i + 1}/{len(urls)}...")
    
    # 3. Deduplicate and Save
    seen = set()
    unique_apis = []
    for api in apis:
        if api["source_url"] not in seen:
            seen.add(api["source_url"])
            unique_apis.append(api)
    
    print(f"[*] Saving {len(unique_apis)} APIs to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(unique_apis, f, indent=2, ensure_ascii=False)
    
    print("[+] Done.")

if __name__ == "__main__":
    main()