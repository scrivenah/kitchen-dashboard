import os
import requests
import datetime
from icalendar import Calendar
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480

def log(msg):
    print(f"LOG: {msg}", flush=True)

# --- 1. GOOGLE CALENDAR FETCHER & PARSER ---
def get_calendar_events():
    ics_urls = os.environ.get("CALENDAR_ICS_URLS", "")
    if not ics_urls:
        log("No CALENDAR_ICS_URLS found in environment.")
        return []

    tz_wa = datetime.timezone(datetime.timedelta(hours=8))
    now_wa = datetime.datetime.now(tz_wa)
    today = now_wa.date()
    tomorrow = today + datetime.timedelta(days=1)

    log(f"Current AWST date: {today} | Tomorrow: {tomorrow}")

    url_list = [u.strip() for u in ics_urls.split(",") if u.strip()]
    log(f"Total calendar URLs provided: {len(url_list)}")

    events = []

    for idx, url in enumerate(url_list):
        safe_url = url[:40] + "..."
        try:
            res = requests.get(url, timeout=12)
            log(f"[Feed #{idx+1}] HTTP {res.status_code} ({safe_url})")
            if res.status_code != 200:
                continue

            cal = Calendar.from_ical(res.text)
            count = 0
            for component in cal.walk():
                if component.name == "VEVENT":
                    count += 1
                    summary = str(component.get("summary", "Untitled"))
                    dtstart_prop = component.get("dtstart")
                    if not dtstart_prop:
                        continue

                    dtstart = dtstart_prop.dt
                    dtend_prop = component.get("dtend")
                    dtend = dtend_prop.dt if dtend_prop else dtstart

                    # Start date & time label
                    if isinstance(dtstart, datetime.datetime):
                        dtstart_local = dtstart.astimezone(tz_wa)
                        start_date = dtstart_local.date()
                        time_str = dtstart_local.strftime("%I:%M %p").lstrip('0')
                    elif isinstance(dtstart, datetime.date):
                        start_date = dtstart
                        time_str = "All Day"
                    else:
                        continue

                    # End date
                    if isinstance(dtend, datetime.datetime):
                        end_date = dtend.astimezone(tz_wa).date()
                    elif isinstance(dtend, datetime.date):
                        end_date = dtend
                    else:
                        end_date = start_date

                    # For all-day events, Google's end date is exclusive
                    if time_str == "All Day" and end_date > start_date:
                        effective_end = end_date - datetime.timedelta(days=1)
                    else:
                        effective_end = end_date

                    # Print out any event within October 2026 for visibility
                    if abs((start_date - today).days) <= 14:
                        log(f"  -> Found '{summary}' | Range: {start_date} to {effective_end} | Time: {time_str}")

                    # Today check
                    if start_date <= today <= effective_end:
                        log(f"     *** ADDED TO TODAY: {summary}")
                        events.append((today, time_str, summary, "TODAY"))

                    # Tomorrow check
                    if start_date <= tomorrow <= effective_end:
                        log(f"     *** ADDED TO TOMORROW: {summary}")
                        events.append((tomorrow, time_str, summary, "TOMORROW"))

            log(f"[Feed #{idx+1}] Evaluated {count} total events.")
        except Exception as e:
            log(f"[Feed #{idx+1}] Exception: {e}")

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for ev in events:
        key = (ev[0], ev[1], ev[2], ev[3])
        if key not in seen:
            seen.add(key)
            deduped.append(ev)

    deduped.sort(key=lambda x: (x[0], 0 if x[1] == "All Day" else 1, x[1]))
    return deduped

# --- 2. ECOWITT DATA FETCHER ---
def get_ecowitt_data():
    app_key = os.environ.get("ECOWITT_APPLICATION_KEY")
    api_key = os.environ.get("ECOWITT_API_KEY")
    mac = os.environ.get("ECOWITT_MAC")

    if not all([app_key, api_key, mac]):
        return None

    url = (
        f"https://api.ecowitt.net/api/v3/device/real_time?"
        f"application_key={app_key}&"
        f"api_key={api_key}&"
        f"mac={mac}&"
        f"call_back=outdoor,rainfall,pressure"
    )
    try:
        res = requests.get(url, timeout=10).json()
        if res.get("code") != 0:
            return None
        
        data = res.get("data", {})
        outdoor = data.get("outdoor", {})
        rainfall = data.get("rainfall", {})

        temp_val = float(outdoor.get("temperature", {}).get("value", 0))
        temp_unit = outdoor.get("temperature", {}).get("unit", "C")
        temp_c = round((temp_val - 32) * 5 / 9, 1) if "F" in temp_unit else round(temp_val, 1)

        humidity = outdoor.get("humidity", {}).get("value", "--")

        def to_mm(metric_dict):
            if not metric_dict:
                return 0.0
            val = float(metric_dict.get("value", 0.0))
            unit = metric_dict.get("unit", "mm")
            return round(val * 25.4, 1) if "in" in unit.lower() else round(val, 1)

        return {
            "temp_c": temp_c,
            "humidity": humidity,
            "rain_event": to_mm(rainfall.get("event")),
            "rain_24h": to_mm(rainfall.get("daily")),
            "rain_weekly": to_mm(rainfall.get("weekly")),
        }
    except Exception as e:
        log(f"Ecowitt error: {e}")
        return None

# --- 3. BOM FORECAST FETCHER ---
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
        log(f"BOM error: {e}")
        return None

calendar_events = get_calendar_events()
ecowitt = get_ecowitt_data()
bom_data = get_balingup_bom()

# --- 4. DRAWING CANVAS ---
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
font_sub = load_font(13)
font_small = load_font(11)

def draw_weather_icon(draw_obj, code, x, y):
    if code in [0, 1]:
        draw_obj.ellipse([x+8, y+8, x+36, y+36], fill=0)
        for p1, p2 in [
            ((x+22, y), (x+22, y+6)), ((x+22, y+38), (x+22, y+44)),
            ((x, y+22), (x+6, y+22)), ((x+38, y+22), (x+44, y+22)),
            ((x+6, y+6), (x+11, y+11)), ((x+33, y+33), (x+38, y+38)),
            ((x+6, y+38), (x+11, y+33)), ((x+33, y+11), (x+38, y+6))
        ]:
            draw_obj.line([p1, p2], fill=0, width=2)
    elif code in [2, 3]:
        draw_obj.ellipse([x+14, y+10, x+38, y+34], fill=0)
        draw_obj.ellipse([x+4, y+18, x+24, y+38], fill=0)
        draw_obj.ellipse([x+20, y+16, x+44, y+38], fill=0)
        draw_obj.rectangle([x+14, y+24, x+36, y+38], fill=0)
    else:
        draw_obj.ellipse([x+14, y+6, x+38, y+30], fill=0)
        draw_obj.ellipse([x+4, y+14, x+24, y+34], fill=0)
        draw_obj.ellipse([x+20, y+12, x+44, y+34], fill=0)
        draw_obj.rectangle([x+14, y+20, x+36, y+34], fill=0)
        for rx in [x+12, x+22, x+32]:
            draw_obj.line([(rx, y+38), (rx-3, y+46)], fill=0, width=2)

# Outer border & header
draw.rectangle([(12, 12), (WIDTH - 12, HEIGHT - 12)], outline=0, width=2)
now_perth = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
date_str = now_perth.strftime("%A, %d %B %Y").upper()
draw.text((24, 22), "BALINGUP DASHBOARD", font=font_title, fill=0)
draw.text((WIDTH - 240, 24), date_str, font=font_small, fill=0)
draw.line([(12, 50), (WIDTH - 12, 50)], fill=0, width=2)

# Split screen
draw.line([(430, 50), (430, HEIGHT - 12)], fill=0, width=2)

# --- LEFT: SCHEDULE & CALENDAR ---
draw.text((24, 62), "TODAY & TOMORROW", font=font_title, fill=0)
draw.line([(24, 86), (410, 86)], fill=0, width=1)

y_pos = 98
if calendar_events:
    for ev_date, time_str, summary, tag in calendar_events[:11]:
        max_chars = 26
        display_summary = summary[:max_chars] + "..." if len(summary) > max_chars else summary
        
        draw.rectangle([(24, y_pos), (116, y_pos + 18)], fill=0)
        draw.text((30, y_pos + 2), tag, font=font_small, fill=1)
        draw.text((124, y_pos + 2), f"{time_str} - {display_summary}", font=font_sub, fill=0)
        y_pos += 28
else:
    draw.text((24, y_pos), "No upcoming events scheduled.", font=font_sub, fill=0)

# --- RIGHT TOP: ECOWITT ---
draw.text((444, 62), "BACKYARD (ECOWITT)", font=font_title, fill=0)
draw.line([(444, 86), (WIDTH - 24, 86)], fill=0, width=1)

if ecowitt:
    draw.text((444, 96), f"{ecowitt['temp_c']}°", font=font_hero, fill=0)
    draw.text((580, 102), f"HUMIDITY: {ecowitt['humidity']}%", font=font_small, fill=0)
    draw.text((580, 120), "STATUS: LIVE ONLINE", font=font_small, fill=0)

    draw.text((444, 150), "RAIN (RESET 9AM):", font=font_sub, fill=0)
    draw.text((444, 170), f"• Today/24h: {ecowitt['rain_24h']} mm", font=font_small, fill=0)
    draw.text((590, 170), f"• Weekly: {ecowitt['rain_weekly']} mm", font=font_small, fill=0)
    draw.text((444, 192), f"• Last Event: {ecowitt['rain_event']} mm", font=font_small, fill=0)
else:
    draw.text((444, 110), "Station Offline or Syncing...", font=font_sub, fill=0)

draw.line([(430, 222), (WIDTH - 12, 222)], fill=0, width=2)

# --- RIGHT BOTTOM: BOM FORECAST ---
draw.text((444, 234), "BOM REGIONAL (BALINGUP)", font=font_title, fill=0)
draw.line([(444, 258), (WIDTH - 24, 258)], fill=0, width=1)

if bom_data:
    draw_weather_icon(draw, bom_data["today"]["code"], 444, 274)
    draw.text((505, 272), f"TODAY: Max {bom_data['today']['max']}°C | Min {bom_data['today']['min']}°C", font=font_sub, fill=0)
    draw.text((505, 294), f"Rain: {bom_data['today']['rain_prob']}% ({bom_data['today']['rain_sum']} mm)", font=font_small, fill=0)

    draw_weather_icon(draw, bom_data["tomorrow"]["code"], 444, 342)
    draw.text((505, 340), f"TOMORROW: Max {bom_data['tomorrow']['max']}°C | Min {bom_data['tomorrow']['min']}°C", font=font_sub, fill=0)
    draw.text((505, 362), f"Rain: {bom_data['tomorrow']['rain_prob']}% ({bom_data['tomorrow']['rain_sum']} mm)", font=font_small, fill=0)
else:
    draw.text((444, 280), "Forecast unavailable", font=font_sub, fill=0)

img.save("dashboard.png", "PNG")
log("Saved complete dashboard preview successfully!")
