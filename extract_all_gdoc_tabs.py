import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    url = "https://docs.google.com/document/d/1sSU_ayA86hPKvDtF5Kc9L6Dter8rzjp_IVZECrSjdjE/edit"
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:43983")
        context = browser.contexts[0]
        page = await context.new_page()
        print(f"Navigating to {url}...")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print("Goto exception:", e)
        await asyncio.sleep(4)

        # Make sure left sidebar tabs panel is visible or open it
        # Look for tab items in the document tabs sidebar
        # In the screenshot, the left panel has "Onglets du document"
        
        # Iterate over all tree items
        # Load existing data if available
        results = {}
        try:
            with open("/root/shein/gdoc_tabs_data.json", "r", encoding="utf-8") as f:
                results = json.load(f)
        except Exception:
            results = {}

        # Get count and names of treeitems
        items = await page.query_selector_all('[role="treeitem"]')
        print(f"Found {len(items)} tree items")
        
        for idx in range(len(items)):
            # Re-query elements to avoid stale references
            items = await page.query_selector_all('[role="treeitem"]')
            el = items[idx]
            name = (await el.inner_text()).strip()
            print(f"\n--- Clicking Tab {idx}: {name} ---")
            await el.click()
            await asyncio.sleep(2)
            
            current_url = page.url
            print(f"Current URL: {current_url}")
            
            # Select all and copy or read export
            tab_id = None
            if "tab=" in current_url:
                tab_id = current_url.split("tab=")[-1].split("&")[0]
                
            export_url = f"https://docs.google.com/document/d/1sSU_ayA86hPKvDtF5Kc9L6Dter8rzjp_IVZECrSjdjE/export?format=txt"
            if tab_id:
                export_url += f"&tab={tab_id}"
                
            text = await page.evaluate("""async (url) => {
                for (let attempt = 0; attempt < 5; attempt++) {
                    try {
                        const res = await fetch(url);
                        if (res.ok) return await res.text();
                        if (res.status === 429) {
                            await new Promise(r => setTimeout(r, 6000 + attempt * 4000));
                            continue;
                        }
                        return "FETCH_ERROR_" + res.status;
                    } catch (e) {
                        await new Promise(r => setTimeout(r, 3000));
                    }
                }
                return "FETCH_ERROR_429_MAX_RETRIES";
            }""", export_url)
            
            print(f"Content length: {len(text)}")
            print(text[:200] + "...")
            
            # Only update if fetched successfully, or if tab didn't exist
            if not text.startswith("FETCH_ERROR_") or name not in results or results[name].get("content", "").startswith("FETCH_ERROR_"):
                results[name] = {
                    "tab_id": tab_id,
                    "url": current_url,
                    "content": text
                }
            
            # Save progress incrementally
            with open("/root/shein/gdoc_tabs_data.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
                
            await asyncio.sleep(3)
            
        print("\nAll tabs saved to /root/shein/gdoc_tabs_data.json")
        await page.close()

if __name__ == "__main__":
    asyncio.run(main())
