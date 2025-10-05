import os
import csv
import re
from typing import List, Dict

SOURCE_DIR = "articles"
OUTPUT_CSV = "extracted_funding_data.csv"

def extract_info_from_text(text: str) -> Dict[str, str]:
    """
    Extract structured data from raw article text.
    Fallback to 'undefined' if data is not found.
    """
    
    info = {
        "company_name": "undefined",
        "funding_amount": "undefined",
        "funding_type": "undefined",
        "article_date": "undefined",
        "company_since": "undefined",
        "article_url": "undefined",
    }

    
    match = re.search(r"^Source:\s*(https?://[^\s]+)", text, re.MULTILINE)
    if match:
        info["article_url"] = match.group(1)

    
    date_match = re.search(r"Date:\s*([\w\s,]+)", text)
    if date_match:
        info["article_date"] = date_match.group(1)
    else:
        
        body_date = re.search(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", text)
        if body_date:
            info["article_date"] = body_date.group(0)

    
    founded_match = re.search(r"\bfounded in (\d{4})", text, re.IGNORECASE)
    if founded_match:
        info["company_since"] = founded_match.group(1)

    
    amount_match = re.search(r"([€$£]\s?\d+(?:[\.,]?\d+)?(?:\s?(?:million|billion|m|k|bn))?)", text, re.IGNORECASE)
    if amount_match:
        info["funding_amount"] = amount_match.group(1).replace("\u00a0", " ")  

    # ----- Extract funding type (look for common types)
    funding_types = ["seed", "pre-seed", "series a", "series b", "series c", "venture", "angel", "growth", "bridge"]
    for ftype in funding_types:
        if re.search(rf"\b{ftype} funding\b", text, re.IGNORECASE):
            info["funding_type"] = ftype.title()
            break

    # ----- Guess company name
    # First line after metadata is usually article title
    lines = text.strip().splitlines()
    for line in lines[2:6]:  # Skip Source/Title headers, scan next few lines
        m = re.match(r"^(.*?)(?:,| has| announced| raises| raised| secured)", line, re.IGNORECASE)
        if m and 2 <= len(m.group(1).split()) <= 5:
            info["company_name"] = m.group(1).strip()
            break

    return info


def extract_all_articles(source_dir: str) -> List[Dict[str, str]]:
    data = []

    for filename in os.listdir(source_dir):
        if filename.endswith(".txt"):
            filepath = os.path.join(source_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()

            print(f"[INFO] Extracting from: {filename}")
            info = extract_info_from_text(text)
            info["filename"] = filename  # track origin file
            data.append(info)

    return data


def save_to_csv(data: List[Dict[str, str]], output_file: str):
    if not data:
        print("[WARN] No data to write.")
        return

    keys = list(data[0].keys())
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

    print(f"[SUCCESS] Extracted data written to {output_file}")


if __name__ == "__main__":
    print("[START] Extracting funding info from articles...")
    extracted_data = extract_all_articles(SOURCE_DIR)
    save_to_csv(extracted_data, OUTPUT_CSV)