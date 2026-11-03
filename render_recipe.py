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
font_title      = load_font("Amazon Ember Bold.ttf", 22)
font_body       = load_font("Amazon Ember.ttf", 18)
font_body_bold  = load_font("Amazon Ember Bold.ttf", 18)

# --- 1. LOAD RECIPE PAYLOAD ---
recipe_data = {"title": "Unknown Recipe", "ingredients": [], "steps": []}
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
steps = recipe_data.get("steps", [])

# Header
draw.rounded_rectangle([(12, 10), (WIDTH - 12, 44)], radius=12, fill=C_WHITE, outline=C_BLACK, width=2)
draw.text((26, 16), title[:60] + "..." if len(title) > 60 else title, font=font_title, fill=C_BLACK)

# Left Column: Ingredients
draw.rounded_rectangle([(12, 54), (300, 468)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)
draw.text((26, 64), "Ingredients", font=font_title, fill=C_BLACK)

y_cursor = 96
for item in ingredients[:12]:
    wrapped_item = wrap_text(f"• {item}", font_body, 260, draw)
    for line in wrapped_item:
        if y_cursor < 445:
            draw.text((26, y_cursor), line, font=font_body, fill=C_BLACK)
            y_cursor += 22 
    y_cursor += 8

# Right Column: Method
draw.rounded_rectangle([(312, 54), (WIDTH - 12, 468)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)
draw.text((326, 64), "Method", font=font_title, fill=C_BLACK)

y_cursor = 96
for i, step in enumerate(steps[:7]):
    wrapped_step = wrap_text(f"{i+1}. {step}", font_body, 440, draw)
    for line in wrapped_step:
        if y_cursor < 445:
            draw.text((326, y_cursor), line, font=font_body, fill=C_BLACK)
            y_cursor += 22 
    y_cursor += 12

# --- 4. STRICT B&W THRESHOLD TO FIX BLEED ---
# Kills all anti-aliased gray pixels so they don't map to orange/yellow in the color palette
img = img.convert("L").point(lambda x: 0 if x < 200 else 255, mode="1").convert("RGB")

img.save("recipe.png", "PNG", optimize=True)
log("Crisp B&W recipe card generated successfully!")
