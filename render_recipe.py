import os
import json
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480

COLOR_BG = (245, 246, 248)
COLOR_CARD = (255, 255, 255)
COLOR_BORDER = (226, 230, 236)
COLOR_PILL_BG = (238, 241, 245)
COLOR_TEXT_DARK = (33, 37, 41)
COLOR_TEXT_MUTED = (100, 110, 122)
COLOR_ACCENT = (234, 88, 12)

img = Image.new('RGB', (WIDTH, HEIGHT), COLOR_BG)
draw = ImageDraw.Draw(img)

def load_font(size, bold=True):
    font_candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans.ttf"
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

font_title = load_font(16.5, bold=True)
font_card_head = load_font(12, bold=True)
font_body = load_font(11.5, bold=False)
font_small = load_font(10, bold=False)
font_num = load_font(11, bold=True)

if not os.path.exists("current_recipe.json"):
    print("No current_recipe.json found.")
    exit(0)

with open("current_recipe.json", "r") as f:
    recipe = json.load(f)

# Header Card
draw.rounded_rectangle([(12, 10), (WIDTH - 12, 50)], radius=18, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)
draw.text((28, 20), recipe.get("title", "Recipe"), font=font_title, fill=COLOR_TEXT_DARK)
# Right-anchored metadata tag to prevent overlap with longer titles
draw.text((WIDTH - 28, 24), recipe.get("meta", ""), font=font_small, fill=COLOR_TEXT_MUTED, anchor="ra")

# Left Column: Ingredients Card
draw.rounded_rectangle([(12, 60), (342, 468)], radius=22, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)
draw.rounded_rectangle([(24, 70), (130, 92)], radius=11, fill=COLOR_PILL_BG, outline=COLOR_BORDER, width=1)
draw.text((36, 75), "Ingredients", font=font_card_head, fill=COLOR_TEXT_DARK)

y_ing = 104
for ing in recipe.get("ingredients", []):
    draw.ellipse([26, y_ing + 4, 32, y_ing + 10], outline=COLOR_ACCENT, width=2)
    clean_ing = ing[:42] + "..." if len(ing) > 44 else ing
    draw.text((42, y_ing), clean_ing, font=font_body, fill=COLOR_TEXT_DARK)
    y_ing += 24

# Right Column: Quick Method Card
draw.rounded_rectangle([(354, 60), (WIDTH - 12, 468)], radius=22, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)
draw.rounded_rectangle([(366, 70), (490, 92)], radius=11, fill=COLOR_PILL_BG, outline=COLOR_BORDER, width=1)
draw.text((380, 75), "Quick Method", font=font_card_head, fill=COLOR_TEXT_DARK)

y_step = 104
MAX_CHARS_PER_LINE = 66

for idx, step in enumerate(recipe.get("steps", [])[:6], 1):
    draw.rounded_rectangle([(366, y_step), (388, y_step + 19)], radius=5, fill=COLOR_PILL_BG)
    draw.text((374, y_step + 3), str(idx), font=font_num, fill=COLOR_ACCENT)

    words = step.split()
    lines = []
    curr = ""
    for w in words:
        if len((curr + " " + w).strip()) <= MAX_CHARS_PER_LINE:
            curr = (curr + " " + w).strip()
        else:
            lines.append(curr)
            curr = w
    if curr:
        lines.append(curr)

    # Render up to 2 wrapped lines per step
    for i, line in enumerate(lines[:2]):
        draw.text((400, y_step + 2 + (i * 16)), line, font=font_body, fill=COLOR_TEXT_DARK)

    # Vertical spacing to ensure 5-6 steps always remain on the card
    y_step += 56 if len(lines) > 1 else 42

img.save("recipe.png", "PNG")
print("Saved recipe.png successfully!")
