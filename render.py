import datetime
from PIL import Image, ImageDraw, ImageFont

# Standard 7.5-inch e-Paper resolution (monochrome 800x480)
WIDTH, HEIGHT = 800, 480

# Create a 1-bit monochrome image (mode '1'), filled with white (255)
img = Image.new('1', (WIDTH, HEIGHT), 255)
draw = ImageDraw.Draw(img)

# Use default bitmap font for the starter test (no external font files needed yet)
# We will upgrade to custom TTF typography later once the pipeline works!
font = ImageFont.load_default()

# 1. Outer Border & Header Banner
draw.rectangle([(10, 10), (WIDTH - 10, HEIGHT - 10)], outline=0, width=2)
today_str = datetime.datetime.now().strftime("%A, %d %B %Y").upper()
draw.text((25, 20), f"KITCHEN DASHBOARD  |  {today_str}", fill=0, font=font)
draw.line([(10, 45), (WIDTH - 10, 45)], fill=0, width=2)

# 2. Vertical Divider (Split screen into Left = Calendar, Right = Weather)
draw.line([(400, 45), (400, HEIGHT - 10)], fill=0, width=2)

# --- LEFT COLUMN: CALENDAR ---
draw.text((25, 55), "TODAY'S SCHEDULE", fill=0, font=font)
draw.line([(25, 70), (380, 70)], fill=0, width=1)

events = [
    "• 07:00 AM - Morning Coffee & Plan",
    "• 09:30 AM - Work Project Review",
    "• 12:30 PM - Lunch",
    "• 04:00 PM - Afternoon Walk",
    "• 06:30 PM - Dinner"
]

y_pos = 85
for event in events:
    draw.text((25, y_pos), event, fill=0, font=font)
    y_pos += 25

# --- RIGHT COLUMN: WEATHER ---
# Top Right: Live Backyard (Ecowitt)
draw.text((420, 55), "BACKYARD STATION (ECOWITT)", fill=0, font=font)
draw.line([(420, 70), (WIDTH - 25, 70)], fill=0, width=1)

draw.text((420, 85), "Temp: 19.5 C  |  Humidity: 58%", fill=0, font=font)
draw.text((420, 110), "Wind: 14 km/h WSW  |  Gust: 22 km/h", fill=0, font=font)
draw.text((420, 135), "Rain Today: 0.0 mm  |  Solar: 450 W/m2", fill=0, font=font)

# Horizontal divider between Ecowitt and BoM
draw.line([(400, 175), (WIDTH - 10, 175)], fill=0, width=1)

# Bottom Right: BoM Forecast
draw.text((420, 190), "BOM / REGIONAL FORECAST", fill=0, font=font)
draw.line([(420, 205), (WIDTH - 25, 205)], fill=0, width=1)

draw.text((420, 220), "Today: Mostly Sunny. Max 24 C. Min 9 C.", fill=0, font=font)
draw.text((420, 245), "Rain Chance: 10% (0 mm)", fill=0, font=font)
draw.text((420, 275), "Tomorrow: Partly Cloudy. Max 22 C.", fill=0, font=font)
draw.text((420, 300), "Rain Chance: 20% (0 - 1 mm)", fill=0, font=font)

# 3. Save as the target dashboard image
img.save("dashboard.png", "PNG")
print("Successfully generated dashboard.png!")
