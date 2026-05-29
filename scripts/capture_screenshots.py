"""Capture screenshots for GitHub README using Playwright."""
import asyncio
from playwright.async_api import async_playwright
import os

OUTPUT_DIR = "E:/agentlearn/gold/docs/screenshots"
BASE_URL = "http://localhost:3000"

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
        )
        page = await context.new_page()

        # 1. Home/Analyze page - initial empty state
        print("1. Capturing analyze page (initial state)...")
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{OUTPUT_DIR}/01-analyze-initial.png", full_page=True)
        print("   -> 01-analyze-initial.png")

        # 2. Analyze a fund (161725)
        print("2. Entering fund code 161725...")
        input_field = page.locator('input[placeholder*="基金代码"]')
        await input_field.fill("161725")
        analyze_btn = page.locator('button.analyze-btn')
        await analyze_btn.click()
        print("   Waiting for API response (up to 15s)...")
        await page.wait_for_timeout(15000)
        await page.screenshot(path=f"{OUTPUT_DIR}/02-analyze-result.png", full_page=True)
        print("   -> 02-analyze-result.png")

        # 3. Portfolio page
        print("3. Capturing portfolio page...")
        portfolio_tab = page.locator('button.main-tab').nth(1)
        await portfolio_tab.click()
        await page.wait_for_timeout(2000)
        await page.screenshot(path=f"{OUTPUT_DIR}/03-portfolio.png", full_page=True)
        print("   -> 03-portfolio.png")

        # 4. Macro dashboard
        print("4. Capturing macro dashboard...")
        macro_tab = page.locator('button.main-tab').nth(2)
        await macro_tab.click()
        await page.wait_for_timeout(5000)
        await page.screenshot(path=f"{OUTPUT_DIR}/04-macro-dashboard.png", full_page=True)
        print("   -> 04-macro-dashboard.png")

        await browser.close()
        print("\nDone! All screenshots saved to docs/screenshots/")

if __name__ == "__main__":
    asyncio.run(main())
