import json
import os
from PIL import Image, ImageDraw, ImageFont

# Screen Dimensions
WIDTH = 800
HEIGHT = 480

# Warm Neutral E-Paper Palette
COLOR_BG = (245, 245, 247)
COLOR_CARD = (255, 255, 255)
COLOR_BORDER = (226, 226, 230)
COLOR_TEXT_DARK = (30, 30, 32)
COLOR_TEXT_MUTED = (110, 110, 115)
COLOR_PILL_BG = (235, 238, 245)
COLOR_STEP_BG = (242, 243, 245)
COLOR_ACCENT = (217, 83, 30)

def load_fonts():
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf"
    ]
    regular_path = next((p for p in font_paths if "Bold" not in p and os.path.exists(p)), None)
    bold_path = next((p for p in font_paths if "Bold" in p and os.path.exists(p)), regular_path)

    if regular_path and bold_path:
        font_title = ImageFont.truetype(bold_path, 20)
        font_meta = ImageFont.truetype(regular_path, 13)
        font_card_head = ImageFont.truetype(bold_path, 13)
        font_body = ImageFont.truetype(regular_path, 12)
        font_step_num = ImageFont.truetype(bold_path, 13)
    else:
        font_title = ImageFont.load_default()
        font_meta = font_card_head = font_body = font_step_num = font_title

    return font_title, font_meta, font_card_head, font_body, font_step_num

def wrap_text(text, max_chars):
    words = text.split()
    lines = []
    curr = ""
    for w in words:
        if len((curr + " " + w).strip()) <= max_chars:
            curr = (curr + " " + w).strip()
        else:
            lines.append(curr)
            curr = w
    if curr:
        lines.append(curr)
    return lines

def render():
    with open("current_recipe.json", "r") as f:
        recipe = json.load(f)

    img = Image.new("RGB", (WIDTH, HEIGHT), COLOR_BG)
    draw = ImageDraw.Draw(img)

    font_title, font_meta, font_card_head, font_body, font_step_num = load_fonts()

    # Header Card
    draw.rounded_rectangle([(12, 10), (788, 48)], radius=18, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)
    draw.text((28, 19), recipe.get("title", "Kitchen Recipe"), font=font_title, fill=COLOR_TEXT_DARK)
    
    meta_text = recipe.get("meta", "")
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), meta_text, font=font_meta)
        meta_w = bbox[2] - bbox[0]
    else:
        meta_w = len(meta_text) * 7
    draw.text((772 - meta_w, 23), meta_text, font=font_meta, fill=COLOR_TEXT_MUTED)

    # Left Column: Ingredients Card
    draw.rounded_rectangle([(12, 58), (342, 468)], radius=22, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)
    draw.rounded_rectangle([(24, 68), (130, 90)], radius=11, fill=COLOR_PILL_BG, outline=COLOR_BORDER, width=1)
    draw.text((36, 73), "Ingredients", font=font_card_head, fill=COLOR_TEXT_DARK)

    y_ing = 102
    MAX_ING_CHARS = 38
    for ing in recipe.get("ingredients", [])[:8]:
        lines = wrap_text(ing, MAX_ING_CHARS)
        
        # Bullet circle
        draw.ellipse([26, y_ing + 3, 32, y_ing + 9], outline=COLOR_ACCENT, width=2)

        # Render up to 3 lines per grouped ingredient item
        for i, line in enumerate(lines[:3]):
            draw.text((42, y_ing + (i * 15)), line, font=font_body, fill=COLOR_TEXT_DARK)

        y_ing += 14 + (len(lines[:3]) * 15)

    # Right Column: Method Steps Card
    draw.rounded_rectangle([(354, 58), (788, 468)], radius=22, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)
    draw.rounded_rectangle([(366, 68), (476, 90)], radius=11, fill=COLOR_PILL_BG, outline=COLOR_BORDER, width=1)
    draw.text((378, 73), "Quick Method", font=font_card_head, fill=COLOR_TEXT_DARK)

    y_step = 102
    MAX_STEP_CHARS = 54
    for idx, step in enumerate(recipe.get("steps", [])[:6], start=1):
        lines = wrap_text(step, MAX_STEP_CHARS)
        
        # Step number badge
        draw.rounded_rectangle([(368, y_step), (390, y_step + 20)], radius=4, fill=COLOR_STEP_BG)
        draw.text((376, y_step + 2), str(idx), font=font_step_num, fill=COLOR_ACCENT)

        # Step text
        for i, line in enumerate(lines[:3]):
            draw.text((404, y_step + 2 + (i * 15)), line, font=font_body, fill=COLOR_TEXT_DARK)

        y_step += max(28, (len(lines[:3]) * 15) + 12)

    img.save("recipe.png")
    print("Saved rendered image to recipe.png")

if __name__ == "__main__":
    render()
