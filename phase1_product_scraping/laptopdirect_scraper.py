import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_laptops_direct():
    results = []
    total_pages = 5

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        page = await browser.new_page()

        for page_num in range(1, total_pages + 1):
            try:
                url = f"https://www.laptopsdirect.co.uk/ct/laptops-and-netbooks/laptops?pageNumber={page_num}"
                print(f"[{page_num}/{total_pages}] Visiting: {url}")

                await page.goto(url, timeout=60000)
                await page.wait_for_timeout(3000)

                cards = await page.query_selector_all("div.OfferBox")
                print(f"  -> Found {len(cards)} products on page {page_num}")

                for card in cards:
                    try:
                        # Title + URL
                        title_el = await card.query_selector("div.OfferBoxTitle a")
                        title = await title_el.inner_text() if title_el else "N/A"
                        product_url = await title_el.get_attribute("href") if title_el else "N/A"
                        if product_url and not product_url.startswith("http"):
                            product_url = "https://www.laptopsdirect.co.uk" + product_url

                        # Price
                        price_el = await card.query_selector("div.OfferBoxPrice")
                        price = await price_el.inner_text() if price_el else "N/A"

                        # Product ID
                        prod_info_el = await card.query_selector("div[id^='productInfo_']")
                        prod_id = "N/A"
                        if prod_info_el:
                            prod_id_attr = await prod_info_el.get_attribute("id")
                            prod_id = prod_id_attr.replace("productInfo_", "") if prod_id_attr else "N/A"

                        # Specs
                        spec_els = await card.query_selector_all("div.OfferBoxProdInfo li")
                        specs = []
                        for s in spec_els:
                            text = await s.inner_text()
                            if text.strip():
                                specs.append(text.strip())

                        # Stock
                        stock_el = await card.query_selector("div.OfferBoxProdInfo span[class*='stock']")
                        stock = await stock_el.inner_text() if stock_el else "N/A"

                        results.append({
                            "title": title.strip(),
                            "product_id": prod_id,
                            "price": price.strip(),
                            "stock_status": stock.strip(),
                            "specs": specs,
                            "product_url": product_url,
                            "page_number": page_num
                        })

                    except Exception as e:
                        print(f"  -> Error on card: {e}")
                        continue

                # Save after every 5 pages in case of crash
                if page_num % 5 == 0:
                    with open("laptops_all.json", "w", encoding="utf-8") as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                    print(f"  -> Progress saved! Total so far: {len(results)} laptops")

                # Delay between pages to avoid getting blocked
                await page.wait_for_timeout(2000)

            except Exception as e:
                print(f"Error on page {page_num}: {e} — skipping")
                continue

        await browser.close()

    # Final save
    with open("./scraped_data/laptops_direct.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done! Total laptops scraped: {len(results)}")
    print("Saved to laptops_direct.json")
    return results

if __name__ == "__main__":
    asyncio.run(scrape_laptops_direct())