import os
import requests
import datetime
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480

# 1. Fetch live BOM ACCESS-G data for Balingup WA (-33.7865, 115.9838)
def get_balingup_bom():
url = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude=-33.7865&longitude=115.9838&"
        "models=bom_access_global&"
        "daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max&"
        "timezone=Australia%2FPerth"
    )
    try:
        res = requests.get(url, timeout=10).json()
        daily = res["daily"]
        return {
            "today": {
                "code": daily["weather_code"][0],
                "max": round(daily["temperature_2m_max"][0]),
                "min": round(daily["temperature_2m_min"][0]),
                "rain_sum": daily.get("precipitation_sum", [0, 0])[0] or 0.0,
                "rain_prob": daily.get("precipitation_probability_max", [0, 0])[0] or 0,
            },
            "tomorrow": {
                "code": daily["weather_code"][1],
                "max": round(daily["temperature_2m_max"][1]),
                "min": round(daily["temperature_2m_min"][1]),
                "rain_sum": daily.get("precipitation_sum", [0, 0])[1] or 0.0,
                "rain_prob": daily.get("precipitation_probability_max", [0, 0])[1] or 0,
            }
        }
    except Exception as e:
        print(f"Error fetching BOM: {e}")
        return None

bom_data = get_balingup_bom()

# 2. Setup Image Canvas (1-bit monochrome)
img = Image.new('1', (WIDTH, HEIGHT), 255)
draw = ImageDraw.Draw(img)

# Load fonts (using downloaded DejaVu/Liberation or fallback to default)
def load_font(size):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "DejaVuSans.ttf"
    ]
    for p in font_paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

font_hero = load_font(46)
font_title = load_font(20)
font_sub = load_font(15)
font_small = load_font(13)

# 3. Geometric Weather Icon Drawer
def draw_weather_icon(draw_obj, code, x, y):
    # Codes 0-1: Sunny / Clear
    if code in [0, 1]:
        draw_obj.ellipse([x+10, y+10, x+40, y+40], fill=0) # Solid sun
        for angle in [(x+25, y-2, x+25, y+6), (x+25, y+44, x+25, y+52),
                      (x-2, y+25, x+6, y+25), (x+44, y+25, x+52, y+25)]:
            draw_obj.line(angle, fill=0, width=2)
    # Codes 2-3: Partly Cloudy / Overcast
    elif code in [2, 3]:
        draw_obj.ellipse([x+15, y+10, x+42, y+37], fill=0)
        draw_obj.ellipse([x+5, y+20, x+28, y+43], fill=0)
        draw_obj.ellipse([x+22, y+18, x+50, y+43], fill=0)
        draw_obj.rectangle([x+15, y+28, x+40, y+43], fill=0)
    # Codes 51-67, 80-82: Rain / Showers
    else:
        # Cloud base
        draw_obj.ellipse([x+12, y+8, x+38, y+34], fill=0)
        draw_obj.ellipse([x+2, y+18, x+26, y+38], fill=0)
        draw_obj.ellipse([x+24, y+16, x+48, y+38], fill=0)
        draw_obj.rectangle([x+12, y+26, x+36, y+38], fill=0)
        # Rain strokes
        for rx in [x+10, x+22, x+34]:
            draw_obj.line([(rx, y+44), (rx-4, y+52)], fill=0, width=2)

# --- LAYOUT RENDERING ---

# Outer border
draw.rectangle([(12, 12), (WIDTH - 12, HEIGHT - 12)], outline=0, width=2)

# Top Header Banner
now_perth = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
date_str = now_perth.strftime("%A, %d %B %Y").upper()
draw.text((26, 22), "BALINGUP DASHBOARD", font=font_title, fill=0)
draw.text((WIDTH - 240, 26), date_str, font=font_small, fill=0)
draw.line([(12, 54), (WIDTH - 12, 54)], fill=0, width=2)

# Vertical Split (Left = Schedule & Tasks, Right = Ecowitt & BOM)
draw.line([(410, 54), (410, HEIGHT - 12)], fill=0, width=2)

# --- LEFT: SCHEDULE & TASKS ---
draw.text((28, 66), "TODAY & TOMORROW", font=font_title, fill=0)
draw.line([(28, 92), (390, 92)], fill=0, width=1)

schedule_mock = [
    ("TODAY", "08:30 AM", "Mine Planning Standup"),
    ("TODAY", "01:00 PM", "Balingup Cottage Review"),
    ("TODAY", "05:30 PM", "Gravel Loop Training Ride"),
    ("TOMORROW", "09:00 AM", "Contractor Site Inspection"),
    ("TASK", "[ ]", "Clean Ecowitt rain funnel"),
    ("TASK", "[ ]", "Bottle conditioned IPA sample"),
]

y_pos = 106
for tag, time_str, desc in schedule_mock:
    # Pill tag (widened to 115 so TOMORROW never clips)
    draw.rectangle([(28, y_pos), (115, y_pos + 18)], fill=0)
    draw.text((34, y_pos + 2), tag, font=font_small, fill=1) # Inverted white text
    draw.text((125, y_pos + 2), f"{time_str} - {desc}", font=font_sub, fill=0)
    y_pos += 30

# --- RIGHT TOP: ECOWITT (PREVIOUS 24H & CYCLES) ---
draw.text((426, 66), "BACKYARD (ECOWITT HISTORY)", font=font_title, fill=0)
draw.line([(426, 92), (WIDTH - 28, 92)], fill=0, width=1)

# Large stats layout
draw.text((426, 102), "18.4°", font=font_hero, fill=0)
draw.text((560, 108), "YESTERDAY HIGH: 23.1°C", font=font_small, fill=0)
draw.text((560, 126), "OVERNIGHT LOW:  7.8°C", font=font_small, fill=0)

draw.text((426, 160), "RAIN (RESET 9AM):", font=font_sub, fill=0)
draw.text((426, 180), "• Prev 24h: 3.2 mm", font=font_small, fill=0)
draw.text((570, 180), "• Weekly Total: 18.6 mm", font=font_small, fill=0)
draw.text((426, 202), "• Last Event: 4.8 mm", font=font_small, fill=0)

# Horizontal Divider between Ecowitt and BOM
draw.line([(410, 230), (WIDTH - 12, 230)], fill=0, width=2)

# --- RIGHT BOTTOM: BOM FORECAST WITH ICONS ---
draw.text((426, 242), "BOM REGIONAL (BALINGUP)", font=font_title, fill=0)
draw.line([(426, 268), (WIDTH - 28, 268)], fill=0, width=1)

if bom_data:
    # Today Card
    draw_weather_icon(draw, bom_data["today"]["code"], 426, 280)
    draw.text((485, 278), f"TODAY: Max {bom_data['today']['max']}°C | Min {bom_data['today']['min']}°C", font=font_sub, fill=0)
    draw.text((485, 300), f"Rain: {bom_data['today']['rain_prob']}% ({bom_data['today']['rain_sum']} mm)", font=font_small, fill=0)

    # Tomorrow Card
    draw_weather_icon(draw, bom_data["tomorrow"]["code"], 426, 345)
    draw.text((485, 343), f"TOMORROW: Max {bom_data['tomorrow']['max']}°C | Min {bom_data['tomorrow']['min']}°C", font=font_sub, fill=0)
    draw.text((485, 365), f"Rain: {bom_data['tomorrow']['rain_prob']}% ({bom_data['tomorrow']['rain_sum']} mm)", font=font_small, fill=0)

img.save("dashboard.png", "PNG")
print("Saved modern dashboard preview!")
