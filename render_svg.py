from playwright.sync_api import sync_playwright
from PIL import Image

svg_path = '/Users/spark/pycharmproject/deva/docs/naja/liquidity_prediction_mobile.svg'
png_path = '/Users/spark/pycharmproject/deva/docs/naja/liquidity_prediction_mobile.png'

with open(svg_path, 'r', encoding='utf-8') as f:
    svg_content = f.read()

html_content = '''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0F172A; width: 800px; }
svg { display: block; width: 800px; height: auto; }
</style>
</head>
<body>''' + svg_content + '''</body>
</html>'''

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 800, 'height': 1688})

    page.set_content(html_content, wait_until='domcontentloaded', timeout=60000)

    height = page.evaluate("document.body.scrollHeight")
    print(f"Content height: {height}")

    page.set_viewport_size({'width': 800, 'height': min(int(height), 20000)})
    page.wait_for_timeout(3000)

    page.screenshot(path=png_path, full_page=True, timeout=120000)
    browser.close()

print(f"Saved to {png_path}")
img = Image.open(png_path)
print(f"Final size: {img.size}")
