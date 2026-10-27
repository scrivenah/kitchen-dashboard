# Playwright Snapshot with 2x Supersampling for Crisp Vector Glyphs
temp_path = "temp_capture.png"
with sync_playwright() as p:
    browser = p.chromium.launch()
    # device_scale_factor=2 captures at 1600x960 retina density
    page = browser.new_page(
        viewport={"width": WIDTH, "height": HEIGHT},
        device_scale_factor=2.0
    )
    page.goto(f"file://{os.path.abspath('rendered_page.html')}")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=temp_path)
    browser.close()

# High-quality downsampling back to 800x480 (Kindle-style anti-aliasing)
from PIL import Image

raw_img = Image.open(temp_path)
# Resample using LANCZOS for razor-sharp letter edges without jagged staircases
final_img = raw_img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).convert('RGB')
final_img.save("dashboard.png", "PNG", optimize=True)

if os.path.exists(temp_path):
    os.remove(temp_path)

log("Rendered crisp, supersampled dashboard to dashboard.png")
