import asyncio
import re
import json
from datetime import datetime
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright


BASE_URL = "https://www.argos.co.uk"
SEARCH_URL = "https://www.argos.co.uk/search/{term}/opt/page:{page}/"
OUTPUT_FILE = "argos_full_structured.json"


def parse_price(text: str) -> float:
    match = re.search(r'(\d+(?:\.\d+)?)', text.replace(",", ""))
    return float(match.group(1)) if match else 0.0


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_product_id_from_url(url: str) -> str:
    match = re.search(r"/product/(\d+)", url)
    return match.group(1) if match else ""


def extract_brand(name: str) -> str:
    if not name:
        return ""
    return name.split()[0].strip()


def extract_model_and_part_numbers(specs: list[str]) -> tuple[str, str]:
    model_number = ""
    part_number = ""

    for spec in specs:
        s = normalize_space(spec)
        m1 = re.search(r"Model number:\s*(.+)", s, re.I)
        if m1:
            model_number = m1.group(1).strip().rstrip(".")
        m2 = re.search(r"Part number:\s*(.+)", s, re.I)
        if m2:
            part_number = m2.group(1).strip().rstrip(".")

    return model_number, part_number


def extract_key_specs_from_text(text: str) -> dict:
    specs = {
        "processor": "",
        "ram": "",
        "storage": "",
        "screen_size": "",
        "gpu": "",
        "os": "",
        "battery": "",
        "weight": "",
    }

    if not text:
        return specs

    clean_text = normalize_space(text)

    cpu_patterns = [
        r"(Intel\s+Core\s+Ultra\s*\d+\s*[\w-]*)",
        r"(Intel\s+Core\s+i[3579]\s*[\w-]*)",
        r"(Intel\s+Celeron\s+[\w-]+)",
        r"(Intel\s+Pentium\s+[\w-]+)",
        r"(Intel\s+Processor\s+[\w-]+)",
        r"(Intel\s+N\d{3,4})",
        r"(AMD\s+Ryzen\s+\d+\s*[\w-]*)",
        r"(AMD\s+A\d+\s*[\w-]*)",
        r"(Apple\s+M\d+\s*(?:Pro|Max|Ultra)?)",
        r"(MediaTek\s+[\w-]+)",
        r"(Snapdragon\s+[\w-]+)",
    ]
    for pattern in cpu_patterns:
        m = re.search(pattern, clean_text, re.I)
        if m:
            specs["processor"] = m.group(1).strip()
            break

    ram_patterns = [
        r"(\d+)\s*GB\s*RAM",
        r"(\d+)\s*GB\s*LPDDR\d*X?",
        r"(\d+)\s*GB\s*DDR\d*",
        r"(\d+)\s*GB\s*memory",
    ]
    for pattern in ram_patterns:
        m = re.search(pattern, clean_text, re.I)
        if m:
            specs["ram"] = f"{m.group(1)}GB"
            break

    storage_patterns = [
        r"(\d+)\s*(TB|GB)\s*(SSD|HDD|eMMC|UFS|eUFS)",
        r"(\d+)\s*(TB|GB)\s*storage",
    ]
    for pattern in storage_patterns:
        m = re.search(pattern, clean_text, re.I)
        if m:
            specs["storage"] = f"{m.group(1)}{m.group(2).upper()}"
            break

    m = re.search(r"(\d+\.?\d*)\s*(?:inch|in)\s*screen", clean_text, re.I)
    if not m:
        m = re.search(r"(\d+\.?\d*)\s*(?:inch|in)\b", clean_text, re.I)
    if m:
        specs["screen_size"] = f'{m.group(1)}"'

    gpu_patterns = [
        r"(NVIDIA\s+RTX\s*\d+\s*(?:Series)?(?:\s*RTX\s*\d+)?)",
        r"(RTX\s*\d+\w*)",
        r"(GTX\s*\d+\w*)",
        r"(RX\s*\d+\w*)",
        r"(Intel\s+Iris\s+Xe)",
        r"(Intel\s+UHD\s+Graphics)",
        r"(Intel\s+Arc\s*[\w-]*)",
        r"(AMD\s+Radeon[\w\s-]*)",
        r"(Integrated graphics)",
    ]
    for pattern in gpu_patterns:
        m = re.search(pattern, clean_text, re.I)
        if m:
            specs["gpu"] = m.group(1).strip().rstrip(".")
            break

    os_patterns = [
        r"(Windows\s+11\s+Pro)",
        r"(Windows\s+11)",
        r"(Windows\s+10)",
        r"(Chrome\s*OS)",
        r"(Google\s+Chrome\s+OS)",
        r"(macOS[\w\s-]*)",
    ]
    for pattern in os_patterns:
        m = re.search(pattern, clean_text, re.I)
        if m:
            specs["os"] = m.group(1).strip()
            break

    m = re.search(r"Up to\s+([\d.]+)\s+hours?\s+battery", clean_text, re.I)
    if not m:
        m = re.search(r"Up to\s+([\d.]+)\s+hours?\b", clean_text, re.I)
    if m:
        specs["battery"] = f"{m.group(1)} hours"

    m = re.search(r"Weight\s+([\d.]+)\s*kg", clean_text, re.I)
    if not m:
        m = re.search(r"(\d+\.?\d*)\s*kg", clean_text, re.I)
    if m:
        specs["weight"] = f"{m.group(1)}kg"

    return specs


async def extract_product_details(page, product_url: str) -> dict:
    await page.goto(product_url, timeout=60000, wait_until="domcontentloaded")

    try:
        await page.wait_for_selector("#pdp-description", timeout=10000)
    except Exception:
        return {
            "specs": [],
            "processor": "",
            "ram": "",
            "storage": "",
            "screen_size": "",
            "gpu": "",
            "os": "",
            "battery": "",
            "weight": "",
            "sku": "",
        }

    desc_root = await page.query_selector("#pdp-description .product-description-content-text")
    if not desc_root:
        return {
            "specs": [],
            "processor": "",
            "ram": "",
            "storage": "",
            "screen_size": "",
            "gpu": "",
            "os": "",
            "battery": "",
            "weight": "",
            "sku": "",
        }

    children = await desc_root.query_selector_all(":scope > p, :scope > ul")
    specs = []
    current_section = ""

    for el in children:
        tag = await el.evaluate("node => node.tagName")
        if tag == "P":
            text = normalize_space(await el.inner_text())
            if not text:
                continue

            if text.endswith(":"):
                current_section = text[:-1].strip()
            else:
                specs.append(text)

        elif tag == "UL":
            lis = await el.query_selector_all("li")
            for li in lis:
                txt = normalize_space(await li.inner_text())
                if not txt:
                    continue
                if current_section:
                    specs.append(f"{current_section}: {txt}")
                else:
                    specs.append(txt)

    full_text = " ".join(specs)
    key_specs = extract_key_specs_from_text(full_text)

    fallback_text = normalize_space(full_text)
    fallback_specs = extract_key_specs_from_text(fallback_text)

    for key in key_specs:
        if not key_specs[key]:
            key_specs[key] = fallback_specs[key]

    model_number, part_number = extract_model_and_part_numbers(specs)
    sku = part_number or model_number

    return {
        "specs": specs,
        "processor": key_specs["processor"],
        "ram": key_specs["ram"],
        "storage": key_specs["storage"],
        "screen_size": key_specs["screen_size"],
        "gpu": key_specs["gpu"],
        "os": key_specs["os"],
        "battery": key_specs["battery"],
        "weight": key_specs["weight"],
        "sku": sku,
    }


async def scrape_argos(category: str = "laptops", max_pages: int = 1, output_file: str = OUTPUT_FILE):
    all_products = []
    global_counter = 1
    seen_product_ids = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        listing_page = await context.new_page()
        detail_page = await context.new_page()

        for page_num in range(1, max_pages + 1):
            search_url = SEARCH_URL.format(term=category, page=page_num)
            print(f"\n[Argos] Page {page_num} → {search_url}")

            await listing_page.goto(search_url, timeout=60000, wait_until="domcontentloaded")

            if page_num == 1:
                for selector in [
                    "button#consent_prompt_submit",
                    "button[data-test='consent-accept-all']",
                    "button:has-text('Accept all')",
                    "button:has-text('Accept')",
                    "button:has-text('OK')",
                ]:
                    try:
                        await listing_page.click(selector, timeout=2500)
                        break
                    except Exception:
                        continue

            await listing_page.wait_for_selector('div[data-testid="component-product-card"]', timeout=15000)

            cards = await listing_page.query_selector_all('div[data-testid="component-product-card"]')
            print(f"[Argos] Found {len(cards)} cards")

            page_count = 0

            for card in cards:
                try:
                    full_text = normalize_space(await card.inner_text())

                    img_el = await card.query_selector("img")
                    name = ""
                    image_url = ""

                    if img_el:
                        name = (await img_el.get_attribute("alt")) or ""
                        image_url = (await img_el.get_attribute("src")) or ""

                    link_el = await card.query_selector("a[href]")
                    href = await link_el.get_attribute("href") if link_el else ""
                    if not href:
                        continue

                    product_url = urljoin(BASE_URL, href)
                    product_id = extract_product_id_from_url(product_url)

                    if not product_id or product_id in seen_product_ids:
                        continue
                    seen_product_ids.add(product_id)

                    price_str = ""
                    price = 0.0
                    price_match = re.search(r"£\s?\d+(?:\.\d+)?", full_text)
                    if price_match:
                        price_str = price_match.group(0).replace(" ", "")
                        price = parse_price(price_str)

                    details = await extract_product_details(detail_page, product_url)

                    combined_text = normalize_space(f"{name} {' '.join(details.get('specs', []))}")
                    combined_specs = extract_key_specs_from_text(combined_text)

                    processor = details.get("processor") or combined_specs["processor"]
                    ram = details.get("ram") or combined_specs["ram"]
                    storage = details.get("storage") or combined_specs["storage"]
                    screen_size = details.get("screen_size") or combined_specs["screen_size"]
                    gpu = details.get("gpu") or combined_specs["gpu"]
                    os_name = details.get("os") or combined_specs["os"]
                    battery = details.get("battery") or combined_specs["battery"]
                    weight = details.get("weight") or combined_specs["weight"]

                    product = {
                        "retailer": "Argos",
                        "name": name,
                        "brand": extract_brand(name),
                        "sku": details.get("sku", ""),
                        "product_id": product_id,
                        "price": price,
                        "price_str": price_str,
                        "category": category,
                        "url": product_url,
                        "processor": processor,
                        "ram": ram,
                        "storage": storage,
                        "screen_size": screen_size,
                        "gpu": gpu,
                        "stock_status": "N/A",
                        "specs": details.get("specs", []),
                        "rating": "",
                        "review_count": "",
                        "image_url": image_url,
                        "scraped_at": datetime.now().isoformat(),
                        "global_id": f"PROD_{global_counter:05d}",
                    }

                    if os_name:
                        product["os"] = os_name
                    if battery:
                        product["battery"] = battery
                    if weight:
                        product["weight"] = weight

                    all_products.append(product)
                    global_counter += 1
                    page_count += 1

                    print(f"[Argos] Added: {name[:70]}")

                except Exception as e:
                    print(f"[Argos] Item error: {e}")

            print(f"[Argos] Page {page_num}: {page_count} products")

        await browser.close()

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)

    print(f"\nDONE ✅ Total products: {len(all_products)}")
    print(f"Saved to: {output_file}")

    return all_products


if __name__ == "__main__":
    pages_to_scrape =2
    category_name ="laptops"

    asyncio.run(scrape_argos(category=category_name, max_pages=pages_to_scrape))