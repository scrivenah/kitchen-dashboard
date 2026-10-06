import os
import requests
import datetime
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480

# 1. Fetch live BOM forecast for Balingup WA (-33.7865, 115.9838)
def get_balingup_bom():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude=-33.7865&longitude=115.9838&"
        "daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max&"
        "timezone=Australia%2FPerth"
    )
    try:
        res = requests.get(url, timeout=10).json()
        daily = res["daily"]
        return {
            "today": {
                "code": daily["weathercode"][0],
                "max": round(daily["temperature_2m_max"][0]),
                "min": round(daily["temperature_2m_min"][0]),
                "rain_sum": daily.get("precipitation_sum", [0, 0])[0] or 0.0,
                "rain_prob": daily.get("precipitation_probability_max", [0, 0])[0] or 0,
            },
            "tomorrow": {
                "code": daily["weathercode"][1],
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

font_hero = load_font(42)
font_title = load_font(18)
font_sub = load_font(14)
font_small = load_font(12)

# 3. Geometric Weather Icon Drawer
def draw_weather_icon(draw_obj, code, x, y):
    # Codes 0-1: Clear / Sunny
    if code in [0, 1]:
        draw_obj.ellipse([x+8, y+8, x+36, y+36], fill=0)
        for p1, p2 in [
            ((x+22, y), (x+22, y+6)),
            ((x+22, y+38), (x+22, y+44)),
            ((x, y+22), (x+6, y+22)),
            ((x+38, y+22), (x+44, y+22)),
            ((x+6, y+6), (x+11, y+11)),
            ((x+33, y+33), (x+38, y+38)),
            ((x+6, y+38), (x+11, y+33)),
            ((x+33, y+11), (x+38, y+6))
        ]:
            draw_obj.line([p1, p2], fill=0, width=2)
    # Codes 2-3: Partly Cloudy / Overcast
    elif code in [2, 3]:
        draw_obj.ellipse([x+14, y+10, x+38, y+34], fill=0)
        draw_obj.ellipse([x+4, y+18, x+24, y+38], fill=0)
        draw_obj.ellipse([x+20, y+16, x+44, y+38], fill=0)
        draw_obj.rectangle([x+14, y+24, x+36, y+38], fill=0)
    # Codes 51-67, 80-82: Rain / Showers
    else:
        draw_obj.ellipse([x+14, y+6, x+38, y+30], fill=0)
        draw_obj.ellipse([x+4, y+14, x+24, y+34], fill=0)
        draw_obj.ellipse([x+20, y+12, x+44, y+34], fill=0)
        draw_obj.rectangle([x+14, y+20, x+36, y+34], fill=0)
        for rx in [x+12, x+22, x+32]:
            draw_obj.line([(rx, y+38), (rx-3, y+46)], fill=0, width=2)

# --- LAYOUT RENDERING ---

# Outer border
draw.rectangle([(12, 12), (WIDTH - 12, HEIGHT - 12)], outline=0, width=2)

# Top Header Banner
now_perth = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
date_str = now_perth.strftime("%A, %d %B %Y").upper()
draw.text((24, 22), "BALINGUP DASHBOARD", font=font_title, fill=0)
draw.text((WIDTH - 240, 24), date_str, font=font_small, fill=0)
draw.line([(12, 50), (WIDTH - 12, 50)], fill=0, width=2)

# Vertical Split (moved to x=430 to give calendar extra room)
draw.line([(430, 50), (430, HEIGHT - 12)], fill=0, width=2)

# --- LEFT: SCHEDULE & TASKS ---
draw.text((24, 62), "TODAY & TOMORROW", font=font_title, fill=0)
draw.line([(24, 86), (410, 86)], fill=0, width=1)

schedule_mock = [
    ("TODAY", "08:30 AM", "Mine Planning Standup"),
    ("TODAY", "01:00 PM", "Balingup Cottage Review"),
    ("TODAY", "05:30 PM", "Gravel Loop Training Ride"),
    ("TOMORROW", "09:00 AM", "Contractor Site Inspection"),
    ("TASK", "[ ]", "Clean Ecowitt rain funnel"),
    ("TASK", "[ ]", "Bottle conditioned IPA sample"),
]

y_pos = 98
for tag, time_str, desc in schedule_mock:
    # Pill tag
    draw.rectangle([(24, y_pos), (116, y_pos + 18)], fill=0)
    draw.text((30, y_pos + 2), tag, font=font_small, fill=1)
    draw.text((124, y_pos + 2), f"{time_str} - {desc}", font=font_sub, fill=0)
    y_pos += 28

# --- RIGHT TOP: ECOWITT (PREVIOUS 24H & CYCLES) ---
draw.text((444, 62), "BACKYARD (ECOWITT HISTORY)", font=font_title, fill=0)
draw.line([(444, 86), (WIDTH - 24, 86)], fill=0, width=1)

draw.text((444, 96), "18.4°", font=font_hero, fill=0)
draw.text((580, 102), "YEST HIGH: 23.1°C", font=font_small, fill=0)
draw.text((580, 120), "NIGHT LOW:  7.8°C", font=font_small, fill=0)

draw.text((444, 150), "RAIN (RESET 9AM):", font=font_sub, fill=0)
draw.text((444, 170), "• Prev 24h: 3.2 mm", font=font_small, fill=0)
draw.text((590, 170), "• Weekly: 18.6 mm", font=font_small, fill=0)
draw.text((444, 192), "• Last Event: 4.8 mm", font=font_small, fill=0)

# Horizontal Divider between Ecowitt and BOM
draw.line([(430, 222), (WIDTH - 12, 222)], fill=0, width=2)

# --- RIGHT BOTTOM: BOM FORECAST WITH ICONS ---
draw.text((444, 234), "BOM REGIONAL (BALINGUP)", font=font_title, fill=0)
draw.line([(444, 258), (WIDTH - 24, 258)], fill=0, width=1)

if bom_data:
    # Today Card
    draw_weather_icon(draw, bom_data["today"]["code"], 444, 274)
    draw.text((505, 272), f"TODAY: Max {bom_data['today']['max']}°C | Min {bom_data['today']['min']}°C", font=font_sub, fill=0)
    draw.text((505, 294), f"Rain: {bom_data['today']['rain_prob']}% ({bom_data['today']['rain_sum']} mm)", font=font_small, fill=0)

    # Tomorrow Card
    draw_weather_icon(draw, bom_data["tomorrow"]["code"], 444, 342)
    draw.text((505, 340), f"TOMORROW: Max {bom_data['tomorrow']['max']}°C | Min {bom_data['tomorrow']['min']}°C", font=font_sub, fill=0)
    draw.text((505, 362), f"Rain: {bom_data['tomorrow']['rain_prob']}% ({bom_data['tomorrow']['rain_sum']} mm)", font=font_small, fill=0)
else:
    draw.text((444, 280), "Forecast unavailable", font=font_sub, fill=0)

img.save("dashboard.png", "PNG")
print("Saved refreshed dashboard preview!")
