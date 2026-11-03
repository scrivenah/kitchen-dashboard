import json
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480

def log(msg):
    print(f"LOG: {msg}", flush=True)

# --- EXACT 7-COLOR E-PAPER PALETTE ---
C_WHITE  = (255, 255, 255)
C_BLACK  = (0, 0, 0)
C_RED    = (255, 0, 0)
C_GREEN  = (0, 255, 0)
C_BLUE   = (0, 0, 255)
C_YELLOW = (255, 255, 0)
C_ORANGE = (255, 128, 0)

def load_font(filename, size):
    try: return ImageFont.truetype(f"font/{filename}", size)
    except: return ImageFont.load_default()

# Enforcing minimum size 18 for readability
font_hero       = load_font("Amazon Ember Bold.ttf", 36)
font_title      = load_font("Amazon Ember Bold.ttf", 22)
font_body       = load_font("Amazon Ember.ttf", 18)
font_body_bold  = load_font("Amazon Ember Bold.ttf", 18)

# --- 1. LOAD RECIPE PAYLOAD ---
recipe_data = {"title": "Unknown Recipe", "ingredients": [], "instructions": []}
try:
    with open("current_recipe.json", "r") as f:
        recipe_data = json.load(f)
    log("Successfully loaded current_recipe.json")
except Exception as e:
    log(f"Error loading recipe JSON: {e}")

# --- 2. TEXT WRAPPING HELPER ---
def wrap_text(text, font, max_width, draw):
    lines = []
    words = text.split()
    current_line = ""
    for word in words:
        test_line = current_line + word + " "
        length = draw.textlength(test_line, font=font)
        if length <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word + " "
    if current_line:
        lines.append(current_line)
    return lines

# --- 3. RENDER CANVAS ---
img = Image.new('RGB', (WIDTH, HEIGHT), C_WHITE)
draw = ImageDraw.Draw(img)

title = recipe_data.get("title", "Recipe").upper()
ingredients = recipe_data.get("ingredients", [])
instructions = recipe_data.get("instructions", [])

# Header
draw.rounded_rectangle([(12, 10), (WIDTH - 12, 58)], radius=14, fill=C_WHITE, outline=C_BLACK, width=2)
draw.text((26, 15), title[:40] + "..." if len(title) > 40 else title, font=font_hero, fill=C_RED)

# Left Column: Ingredients (Width: ~280px)
draw.rounded_rectangle([(12, 68), (300, 468)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)
draw.text((26, 78), "Ingredients", font=font_title, fill=C_BLACK)

y_cursor = 110
for item in ingredients[:12]: # Limit to fit screen
    wrapped_item = wrap_text(f"• {item}", font_body, 260, draw)
    for line in wrapped_item:
        if y_cursor < 440:
            draw.text((26, y_cursor), line, font=font_body, fill=C_BLACK)
            y_cursor += 24

# Right Column: Instructions (Width: ~476px)
draw.rounded_rectangle([(312, 68), (WIDTH - 12, 468)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)
draw.text((326, 78), "Method", font=font_title, fill=C_BLACK)

y_cursor = 110
for i, step in enumerate(instructions[:6]): # Limit to fit screen
    wrapped_step = wrap_text(f"{i+1}. {step}", font_body, 440, draw)
    for line in wrapped_step:
        if y_cursor < 440:
            draw.text((326, y_cursor), line, font=font_body, fill=C_BLACK)
            y_cursor += 24
    y_cursor += 8 # Gap between steps

# --- 4. NO-DITHER QUANTIZATION ---
pal_img = Image.new("P", (1, 1))
pal = [
    255, 255, 255,  # 0: White
    0, 0, 0,        # 1: Black
    255, 0, 0,      # 2: Red
    0, 255, 0,      # 3: Green
    0, 0, 255,      # 4: Blue
    255, 255, 0,    # 5: Yellow
    255, 128, 0     # 6: Orange
]
pal += [0] * (768 - len(pal))
pal_img.putpalette(pal)

# Forces pure palette colors to kill fuzzy gray edge pixels
img = img.quantize(palette=pal_img, dither=0)

img.save("recipe1.png", "PNG", optimize=True)
log("Crisp recipe card generated successfully!")
