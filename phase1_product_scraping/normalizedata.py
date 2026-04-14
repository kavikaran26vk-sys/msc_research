import json
import re
from datetime import datetime
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

ARGOS_FILE = "./scraped_data/argos_laptops.json"
LAPTOPSDIRECT_FILE = "./scraped_data/laptops_direct.json"
OUTPUT_FILE = "./scraped_data/merged_products.json"


# ============================================================
# COMMON HELPERS
# ============================================================

COMMON_KEYS = [
    "retailer",
    "name",
    "brand",
    "sku",
    "product_id",
    "price",
    "price_str",
    "category",
    "url",
    "processor",
    "ram",
    "storage",
    "screen_size",
    "gpu",
    "stock_status",
    "specs",
    "rating",
    "review_count",
    "image_url",
    "scraped_at",
    "global_id"
]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def parse_price_value(text: str) -> float:
    if text is None:
        return 0.0

    text = str(text)
    matches = re.findall(r"£\s*([\d,]+(?:\.\d{1,2})?)", text)
    if matches:
        try:
            return float(matches[-1].replace(",", ""))
        except ValueError:
            pass

    fallback = re.search(r"([\d,]+(?:\.\d{1,2})?)", text)
    if fallback:
        try:
            return float(fallback.group(1).replace(",", ""))
        except ValueError:
            return 0.0

    return 0.0


def format_price_str(price: float) -> str:
    return f"£{price:.2f}" if price else ""


def extract_brand(name: str) -> str:
    name = normalize_space(name)
    if not name:
        return ""
    return name.split()[0]


def extract_os(text: str) -> str:
    text = normalize_space(text)

    patterns = [
        r"(Windows\s+11\s+Pro)",
        r"(Windows\s+11)",
        r"(Windows\s+10)",
        r"(Chrome\s*OS)",
        r"(ChromeOS)",
        r"(Google\s+Chrome\s+OS)",
        r"(macOS[\w\s-]*)",
        r"(DOS)",
        r"(Linux)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            os_name = m.group(1).strip()
            if os_name.lower() == "chromeos":
                return "Chrome OS"
            return os_name

    return ""


def extract_key_specs_from_text(text: str) -> dict:
    specs = {
        "processor": "",
        "ram": "",
        "storage": "",
        "screen_size": "",
        "gpu": ""
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
        r"(Intel\s+UHD\s+graphics)",
        r"(Intel\s+UHD\s+Graphics)",
        r"(Intel\s+Arc\s*[\w-]*)",
        r"(AMD\s+Radeon[\w\s-]*)",
        r"(Integrated graphics)",
        r"(Dedicated graphics card)",
    ]
    for pattern in gpu_patterns:
        m = re.search(pattern, clean_text, re.I)
        if m:
            specs["gpu"] = m.group(1).strip().rstrip(".")
            break

    # specs["os"] = extract_os(clean_text)

    # m = re.search(r"Up to\s+([\d.]+)\s+hours?\s+battery", clean_text, re.I)
    # if not m:
    #     m = re.search(r"Up to\s+([\d.]+)\s+hours?\b", clean_text, re.I)
    # if m:
    #     specs["battery"] = f"{m.group(1)} hours"

    # m = re.search(r"Weight\s+([\d.]+)\s*kg", clean_text, re.I)
    # if not m:
    #     m = re.search(r"(\d+\.?\d*)\s*kg", clean_text, re.I)
    # if m:
    #     specs["weight"] = f"{m.group(1)}kg"

    return specs


def build_common_product(data: dict) -> dict:
    product = {key: "" for key in COMMON_KEYS}
    product["specs"] = []

    for key in COMMON_KEYS:
        if key in data:
            product[key] = data[key]

    if not isinstance(product["specs"], list):
        product["specs"] = []

    return product


# ============================================================
# ARGOS NORMALIZER
# ============================================================

def normalize_argos_item(item: dict, global_index: int) -> dict:
    product = build_common_product(item)

    product["retailer"] = "Argos"
    product["name"] = item.get("name", "")
    product["brand"] = item.get("brand") or extract_brand(product["name"])
    product["sku"] = item.get("sku", "")
    product["product_id"] = str(item.get("product_id", ""))
    product["price"] = float(item.get("price", 0) or 0)
    product["price_str"] = item.get("price_str") or format_price_str(product["price"])
    product["category"] = item.get("category", "laptops")
    product["url"] = item.get("url", "")
    product["processor"] = item.get("processor", "")
    product["ram"] = item.get("ram", "")
    product["storage"] = item.get("storage", "")
    product["screen_size"] = item.get("screen_size", "")
    product["gpu"] = item.get("gpu", "")
    product["stock_status"] = item.get("stock_status", "N/A")
    product["specs"] = item.get("specs", []) or []
    product["rating"] = item.get("rating", "")
    product["review_count"] = item.get("review_count", "")
    product["image_url"] = item.get("image_url", "")
    product["scraped_at"] = item.get("scraped_at") or datetime.now().isoformat()
    product["global_id"] = f"PROD_{global_index:05d}"
    # product["os"] = item.get("os", "")
    # product["battery"] = item.get("battery", "")
    # product["weight"] = item.get("weight", "")

    return product


# ============================================================
# LAPTOPSDIRECT NORMALIZER
# ============================================================

def normalize_laptopsdirect_item(item: dict, global_index: int) -> dict:
    name = item.get("name") or item.get("title", "")
    specs_list = item.get("specs", []) or []
    combined_text = normalize_space(name + " " + " ".join(specs_list))

    extracted = extract_key_specs_from_text(combined_text)

    price_text = item.get("price", "")
    price_value = parse_price_value(price_text)

    # Try to get a clean stock status line from the messy price field
    stock_status = item.get("stock_status", "").strip()
    if not stock_status or stock_status == "N/A":
        stock_match = re.search(
            r"(In Stock|Out of Stock|Pre-Order|Available|Delivery from [^\n]+)",
            str(price_text),
            re.I,
        )
        if stock_match:
            stock_status = stock_match.group(1).strip()
        else:
            stock_status = "N/A"

    sku = item.get("sku", "")

    product = build_common_product({})

    product["retailer"] = "LaptopsDirect"
    product["name"] = name
    product["brand"] = item.get("brand") or extract_brand(name)
    product["sku"] = sku
    product["product_id"] = str(item.get("product_id", ""))
    product["price"] = price_value
    product["price_str"] = format_price_str(price_value)
    product["category"] = item.get("category", "laptops")
    product["url"] = item.get("url") or item.get("product_url", "")
    product["processor"] = item.get("processor", "") or extracted["processor"]
    product["ram"] = item.get("ram", "") or extracted["ram"]
    product["storage"] = item.get("storage", "") or extracted["storage"]
    product["screen_size"] = item.get("screen_size", "") or extracted["screen_size"]
    product["gpu"] = item.get("gpu", "") or extracted["gpu"]
    product["stock_status"] = stock_status
    product["specs"] = specs_list
    product["rating"] = item.get("rating", "")
    product["review_count"] = item.get("review_count", "")
    product["image_url"] = item.get("image_url", "")
    product["scraped_at"] = item.get("scraped_at") or datetime.now().isoformat()
    product["global_id"] = f"PROD_{global_index:05d}"
    # product["os"] = item.get("os", "") or extracted["os"]
    # product["battery"] = item.get("battery", "") or extracted["battery"]
    # product["weight"] = item.get("weight", "") or extracted["weight"]

    return product


# ============================================================
# FILE HELPERS
# ============================================================

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================
# MAIN MERGE LOGIC
# ============================================================

def merge_products(argos_file: str, laptopsdirect_file: str, output_file: str):
    argos_data = load_json(argos_file)
    laptopsdirect_data = load_json(laptopsdirect_file)

    merged = []
    global_index = 1

    for item in argos_data:
        merged.append(normalize_argos_item(item, global_index))
        global_index += 1

    for item in laptopsdirect_data:
        merged.append(normalize_laptopsdirect_item(item, global_index))
        global_index += 1

    save_json(merged, output_file)

    print(f"Argos products        : {len(argos_data)}")
    print(f"LaptopsDirect products: {len(laptopsdirect_data)}")
    print(f"Total merged          : {len(merged)}")
    print(f"Saved to              : {output_file}")

    if merged:
        print("\nSample merged item:")
        print(json.dumps(merged[0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    merge_products(
        argos_file=ARGOS_FILE,
        laptopsdirect_file=LAPTOPSDIRECT_FILE,
        output_file=OUTPUT_FILE,
    )