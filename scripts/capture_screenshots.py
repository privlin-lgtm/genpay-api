"""
Regenerates the Swagger UI screenshots embedded in README.md.

Not part of the app itself — a one-off tool, run manually against a live instance.

Usage:
    pip install -r requirements-dev.txt
    playwright install chromium
    uvicorn app.main:app --port 8813 &
    RECORD_ID=$(curl -s localhost:8813/records | python3 -c "import json,sys;print(json.load(sys.stdin)[0]['id'])")
    USER_ID=$(curl -s -H "X-API-Key: change-me" localhost:8813/users | python3 -c "import json,sys;d=json.load(sys.stdin);print([u for u in d if u['role']=='researcher'][0]['id'])")
    python scripts/capture_screenshots.py "$RECORD_ID" "$USER_ID"
"""

import json
import sys

from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8813"
OUT_DIR = "docs/screenshots"
RECORD_ID = sys.argv[1]
USER_ID = sys.argv[2]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    page.goto(f"{BASE_URL}/docs")
    page.wait_for_selector("text=GenPay API")
    page.screenshot(path=f"{OUT_DIR}/swagger-overview.png")
    print("captured swagger-overview.png")

    # Expand the POST /purchase endpoint to show request/response schema.
    page.get_by_text("/purchase", exact=True).click()
    page.wait_for_timeout(500)
    page.screenshot(path=f"{OUT_DIR}/swagger-purchase-endpoint.png")
    print("captured swagger-purchase-endpoint.png")

    # Try it out: fill headers + body, execute, screenshot the real response.
    page.get_by_role("button", name="Try it out").click()
    page.wait_for_timeout(200)

    inputs = page.locator("table.parameters tr input")
    inputs.nth(0).fill("readme-demo-key-1")  # Idempotency-Key
    inputs.nth(1).fill("change-me")  # x-api-key

    body = {"research_record_id": RECORD_ID, "user_id": USER_ID}
    textarea = page.locator("textarea.body-param__text")
    textarea.fill(json.dumps(body, indent=2))

    page.get_by_role("button", name="Execute").click()
    page.wait_for_selector("text=Server response", timeout=10000)
    page.wait_for_timeout(500)

    response_block = page.locator(".responses-wrapper")
    response_block.scroll_into_view_if_needed()
    page.screenshot(path=f"{OUT_DIR}/swagger-purchase-executed.png")
    print("captured swagger-purchase-executed.png")

    browser.close()
