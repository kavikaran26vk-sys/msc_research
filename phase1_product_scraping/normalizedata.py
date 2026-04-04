import json
import re
from datetime import datetime

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clean_price(price_val):
    """Extract float price from string or number"""
    if isinstance(price_val, (int, float)):
        return float(price_val)
    if isinstance(price_val, str):
        # Remove currency symbols and text, get first price number
        # Handle cases like "SAVE £160\n£593.97\nFrom £21..."
        lines = price_val.split('\n')
        for line in lines:
            line = line.strip()
            # Skip lines that start with SAVE
            if line.upper().startswith('SAVE'):
                continue
            cleaned = re.sub(r'[^\d.]', '', line.replace('£', '').strip())
            if cleaned:
                try:
                    val = float(cleaned)
                    if val > 10:  # skip tiny numbers
                        return val
                except:
                    continue
    return 0.0

def extract_ram(text):
    """Extract RAM value - look for XGB RAM pattern specifically"""
    if not text:
        return ""
    # Priority: explicit RAM mention
    match = re.search(r'(\d+)\s*GB\s*RAM', text, re.IGNORECASE)
    if match:
        return match.group(1) + "GB"
    # Fallback: memory pattern
    match = re.search(r'(\d+)\s*GB\s*(?:memory|LPDDR|DDR)', text, re.IGNORECASE)
    if match:
        return match.group(1) + "GB"
    return ""

def extract_storage(text):
    """Extract storage - must be SSD/HDD/eMMC, NOT just GB"""
    if not text:
        return ""
    # TB SSD first
    match = re.search(r'(\d+)\s*TB\s*(?:SSD|HDD|NVMe|storage)', text, re.IGNORECASE)
    if match:
        return match.group(1) + "TB"
    # GB SSD
    match = re.search(r'(\d+)\s*GB\s*(?:SSD|HDD|NVMe|eMMC|eUFS|storage)', text, re.IGNORECASE)
    if match:
        return match.group(1) + "GB"
    # Just TB
    match = re.search(r'(\d+)\s*TB', text, re.IGNORECASE)
    if match:
        return match.group(1) + "TB"
    return ""

def extract_screen_size(text):
    """Extract screen size"""
    if not text:
        return ""
    match = re.search(r'(\d+\.?\d*)\s*["\']?\s*(?:inch|Inch)?', text, re.IGNORECASE)
    if match:
        val = float(match.group(1))
        if 10 <= val <= 20:  # valid laptop screen range
            return str(val) + '"'
    return ""

def extract_processor(text):
    """Extract processor from text"""
    if not text:
        return ""
    patterns = [
        r'Intel\s+Core\s+Ultra\s+\d+\s+\d+\w*',
        r'Intel\s+Core\s+Ultra\s+\d+',
        r'Intel\s+Core\s+i\d[-\s]\d+\w*',
        r'Intel\s+Core\s+i\d',
        r'Intel\s+Core\s+\d+\s+\d+\w*',
        r'Intel\s+Core\s+\d+',
        r'AMD\s+Ryzen\s+AI\s+\d+\s*\d*\w*',
        r'AMD\s+Ryzen\s+\d+\s+\d+\w*',
        r'AMD\s+Ryzen\s+\d+',
        r'AMD\s+Athlon\s*\w*',
        r'AMD\s+A\d+\w*',
        r'Apple\s+M\d+(?:\s+Pro)?(?:\s+Max)?',
        r'Intel\s+Celeron\s+\w+',
        r'Intel\s+Pentium\s+\w+',
        r'Intel\s+N\d+',
        r'Snapdragon\s+\w+',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return ""

def extract_gpu(text):
    """Extract GPU info from text"""
    if not text:
        return ""
    match = re.search(r'(?:RTX|GTX)\s*\d+\s*\w*', text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    match = re.search(r'RX\s*\d+\w*', text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    match = re.search(r'Intel\s+Arc\s+\w+', text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return ""

def extract_brand_from_name(name):
    """Extract brand from product name"""
    brands = [
        'HP', 'Dell', 'Lenovo', 'Asus', 'Acer', 'Apple', 'MSI',
        'Samsung', 'Toshiba', 'LG', 'Razer', 'Gigabyte', 'Huawei',
        'Microsoft', 'Medion', 'Chuwi', 'Jumper', 'Google'
    ]
    name_upper = name.upper()
    for brand in brands:
        if name_upper.startswith(brand.upper()):
            return brand
    return ""

# ============================================================
# NORMALISE LAPTOPS DIRECT
# ============================================================

def normalise_laptops_direct(filepath):
    print(f"Loading Laptops Direct data from {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    normalised = []
    for i, item in enumerate(data):
        try:
            title = item.get('title', '')
            specs = item.get('specs', [])
            specs_text = ' '.join(specs)
            full_text = title + ' ' + specs_text

            #  Fixed price extraction
            raw_price = item.get('price', '')
            price = clean_price(raw_price)

            # Extract fields
            brand = extract_brand_from_name(title)
            processor = extract_processor(full_text)
            ram = extract_ram(full_text)
            storage = extract_storage(full_text)
            screen_size = extract_screen_size(title)
            gpu = extract_gpu(full_text)

            # SKU from product_id or title
            product_id = str(item.get('product_id', f'{i+1:05d}'))
            sku = item.get('sku', '')

            normalised.append({
                "retailer": "LaptopsDirect",
                "name": title,
                "brand": brand,
                "sku": sku,
                "product_id": f"LD_{product_id}",
                "price": price,
                "price_str": f"£{price:.2f}" if price else "N/A",
                "category": "laptops",
                "url": item.get('product_url', ''),
                "processor": processor,
                "ram": ram,
                "storage": storage,
                "screen_size": screen_size,
                "gpu": gpu,
                "stock_status": item.get('stock_status', ''),
                "specs": specs,
                "rating": "",
                "review_count": "",
                "image_url": "",
                "scraped_at": datetime.now().isoformat(),
            })

        except Exception as e:
            print(f"  Error on LaptopsDirect item {i}: {e}")
            continue

    print(f"  -> Normalised {len(normalised)} Laptops Direct products")
    return normalised


# ============================================================
# NORMALISE ARGOS
# ============================================================

def normalise_argos(filepath):
    print(f"Loading Argos data from {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    normalised = []
    for i, item in enumerate(data):
        try:
            name = item.get('name', '')
            price = clean_price(item.get('price', 0))

            #  Use full name for extraction
            full_text = name

            processor = extract_processor(item.get('processor', '') or full_text)
            ram = extract_ram(item.get('ram', '') or full_text)

            #  Fixed storage — use name only if explicit SSD/HDD keyword present
            storage_field = item.get('storage', '')
            if storage_field and any(x in storage_field.upper() for x in ['SSD', 'HDD', 'TB', 'EMMC']):
                storage = extract_storage(storage_field)
            else:
                storage = extract_storage(full_text)

            screen_size = item.get('screen_size', '') or extract_screen_size(full_text)
            gpu = extract_gpu(full_text)
            brand = item.get('brand', '') or extract_brand_from_name(name)

            # Rating cleanup
            rating_raw = item.get('rating', '')
            rating = re.sub(r'[^\d.]', '', str(rating_raw)) if rating_raw else ''

            normalised.append({
                "retailer": "Argos",
                "name": name,
                "brand": brand,
                "sku": item.get('model', ''),
                "product_id": item.get('product_id', f'ARG_{i+1:05d}'),
                "price": price,
                "price_str": item.get('price_str', f'£{price:.2f}'),
                "category": "laptops",
                "url": item.get('url', ''),
                "processor": processor,
                "ram": ram,
                "storage": storage,
                "screen_size": screen_size,
                "gpu": gpu,
                "stock_status": "In Stock",
                "specs": [],
                "rating": rating,
                "review_count": item.get('review_count', ''),
                "image_url": item.get('image_url', ''),
                "scraped_at": item.get('scraped_at', datetime.now().isoformat()),
            })

        except Exception as e:
            print(f"  Error on Argos item {i}: {e}")
            continue

    
    return normalised


# ============================================================
# MERGE & SAVE
# ============================================================

def merge_and_save(ld_path, argos_path, output_path):
    ld_products = normalise_laptops_direct(ld_path)
    argos_products = normalise_argos(argos_path)

    all_products = ld_products + argos_products

    for i, p in enumerate(all_products):
        p['global_id'] = f"PROD_{i+1:05d}"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)

    print(f"\n Done!")
    print(f"   Laptops Direct : {len(ld_products)} products")
    print(f"   Argos          : {len(argos_products)} products")
    print(f"   Total merged   : {len(all_products)} products")
    print(f"   Saved to       : {output_path}")

    print("\n--- Sample Laptops Direct product ---")
    print(json.dumps(ld_products[0], indent=2))
    print("\n--- Sample Argos product ---")
    print(json.dumps(argos_products[0], indent=2))

    return all_products


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    LAPTOPS_DIRECT_FILE = "laptops_direct.json"
    ARGOS_FILE = "argos_laptops.json"
    OUTPUT_FILE = "products_unified.json"

    merge_and_save(LAPTOPS_DIRECT_FILE, ARGOS_FILE, OUTPUT_FILE)