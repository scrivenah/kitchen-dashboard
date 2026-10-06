import os
import requests
import datetime
from dateutil import rrule as drrule
from icalendar import Calendar
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480

def log(msg):
    print(f"LOG: {msg}", flush=True)

# --- 1. GOOGLE & AIRBNB CALENDAR FETCHER ---
def get_calendar_events():
    ics_urls = os.environ.get("CALENDAR_ICS_URLS", "")
    if not ics_urls:
        log("No CALENDAR_ICS_URLS found in environment.")
        return [], [], []

    tz_wa = datetime.timezone(datetime.timedelta(hours=8))
    now_wa = datetime.datetime.now(tz_wa)
    today = now_wa.date()
    tomorrow = today + datetime.timedelta(days=1)
    future_cutoff = today + datetime.timedelta(days=6)

    url_list = [u.strip() for u in ics_urls.split(",") if u.strip()]
    raw_events = []

    for idx, url in enumerate(url_list):
        is_airbnb = "airbnb" in url.lower()
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code != 200:
                continue

            cal = Calendar.from_ical(res.text)
            for component in cal.walk():
                if component.name == "VEVENT":
                    summary = str(component.get("summary", "Untitled"))
                    if is_airbnb and summary == "Reserved":
                        summary = "Vic's Shack Reserved"

                    dtstart_prop = component.get("dtstart")
                    if not dtstart_prop:
                        continue

                    dtstart = dtstart_prop.dt
                    dtend_prop = component.get("dtend")
                    dtend = dtend_prop.dt if dtend_prop else dtstart

                    is_all_day = not isinstance(dtstart, datetime.datetime)
                    if not is_all_day:
                        dtstart_local = dtstart.astimezone(tz_wa)
                        dtend_local = dtend.astimezone(tz_wa) if isinstance(dtend, datetime.datetime) else dtstart_local
                        base_start_date = dtstart_local.date()
                        base_end_date = dtend_local.date()
                        time_str = dtstart_local.strftime("%I:%M %p").lstrip('0')
                        duration = dtend_local - dtstart_local
                    else:
                        base_start_date = dtstart
                        base_end_date = dtend if isinstance(dtend, datetime.date) else dtstart
                        time_str = ""
                        duration = base_end_date - base_start_date

                    if is_all_day and base_end_date > base_start_date:
                        effective_end = base_end_date - datetime.timedelta(days=1)
                    else:
                        effective_end = base_end_date

                    active_dates = []
                    curr = base_start_date
                    while curr <= effective_end:
                        active_dates.append(curr)
                        curr += datetime.timedelta(days=1)

                    rrule_prop = component.get("rrule")
                    if rrule_prop:
                        try:
                            rule_str = rrule_prop.to_ical().decode("utf-8")
                            rule_start = dtstart if isinstance(dtstart, datetime.datetime) else datetime.datetime.combine(base_start_date, datetime.time.min)
                            parsed_rule = drrule.rrulestr(rule_str, dtstart=rule_start)

                            check_start = datetime.datetime.combine(today - datetime.timedelta(days=7), datetime.time.min)
                            check_end = datetime.datetime.combine(future_cutoff + datetime.timedelta(days=1), datetime.time.max)

                            for occ in parsed_rule.between(check_start, check_end, inc=True):
                                occ_date = occ.date()
                                occ_end_date = (occ + duration).date() if not is_all_day else (occ.date() + duration - datetime.timedelta(days=1 if duration.days > 0 else 0))
                                occ_curr = occ_date
                                while occ_curr <= occ_end_date:
                                    active_dates.append(occ_curr)
                                    occ_curr += datetime.timedelta(days=1)
                        except Exception:
                            pass

                    for d in set(active_dates):
                        if today <= d <= future_cutoff:
                            raw_events.append((d, time_str, summary))

        except Exception as e:
            log(f"Feed error: {e}")

    unique_events = list({(e[0], e[1], e[2]): e for e in raw_events}.values())
    unique_events.sort(key=lambda x: (x[0], 0 if x[1] == "" else 1, x[1]))

    today_events = [e for e in unique_events if e[0] == today]
    tomorrow_events = [e for e in unique_events if e[0] == tomorrow]
    later_events = [e for e in unique_events if e[0] > tomorrow]

    return today_events, tomorrow_events, later_events

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

# --- 3. BOM FORECAST FETCHER (7-DAY OUTLOOK) ---
def get_balingup_bom():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude=-33.7865&longitude=115.9838&"
        "daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max&"
        "models=bom_access_global&"
        "past_days=1&forecast_days=7&"
        "timezone=Australia%2FPerth"
    )
    try:
        res = requests.get(url, timeout=10).json()
        daily = res["daily"]
        dates = [datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in daily["time"]]

        # Index 0 is Yesterday, Index 1 is Today, Index 2 is Tomorrow
        # Indices 3 to 7 are the subsequent 5 days
        upcoming_5_days = []
        for i in range(3, min(8, len(dates))):
            upcoming_5_days.append({
                "date": dates[i],
                "day_name": dates[i].strftime("%a").upper(),
                "code": daily["weathercode"][i]
            })

        return {
            "yesterday": {
                "max": round(daily["temperature_2m_max"][0]),
                "min": round(daily["temperature_2m_min"][0]),
            },
            "today": {
                "code": daily["weathercode"][1],
                "max": round(daily["temperature_2m_max"][1]),
                "min": round(daily["temperature_2m_min"][1]),
                "rain_sum": daily.get("precipitation_sum", [0]*8)[1] or 0.0,
                "rain_prob": daily.get("precipitation_probability_max", [0]*8)[1] or 0,
            },
            "tomorrow": {
                "code": daily["weathercode"][2],
                "max": round(daily["temperature_2m_max"][2]),
                "min": round(daily["temperature_2m_min"][2]),
                "rain_sum": daily.get("precipitation_sum", [0]*8)[2] or 0.0,
                "rain_prob": daily.get("precipitation_probability_max", [0]*8)[2] or 0,
            },
            "next_5_days": upcoming_5_days
        }
    except Exception as e:
        log(f"BOM error: {e}")
        return None

today_events, tomorrow_events, later_events = get_calendar_events()
ecowitt = get_ecowitt_data()
bom = get_balingup_bom()

# --- 4. RENDER CANVAS ---
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
font_title = load_font(16)
font_card_head = load_font(12)
font_sub = load_font(12)
font_small = load_font(10)
font_tiny_bold = load_font(9)

def draw_weather_icon(draw_obj, code, x, y):
    if code in [0, 1]:  # Sun
        draw_obj.ellipse([x+8, y+8, x+36, y+36], fill=0)
        for p1, p2 in [
            ((x+22, y), (x+22, y+6)), ((x+22, y+38), (x+22, y+44)),
            ((x, y+22), (x+6, y+22)), ((x+38, y+22), (x+44, y+22)),
            ((x+6, y+6), (x+11, y+11)), ((x+33, y+33), (x+38, y+38)),
            ((x+6, y+38), (x+11, y+33)), ((x+33, y+11), (x+38, y+6))
        ]:
            draw_obj.line([p1, p2], fill=0, width=2)
    elif code in [2, 3]:  # Clouds
        draw_obj.ellipse([x+14, y+10, x+38, y+34], fill=0)
        draw_obj.ellipse([x+4, y+18, x+24, y+38], fill=0)
        draw_obj.ellipse([x+20, y+16, x+44, y+38], fill=0)
        draw_obj.rectangle([x+14, y+24, x+36, y+38], fill=0)
    else:  # Rain
        draw_obj.ellipse([x+14, y+6, x+38, y+30], fill=0)
        draw_obj.ellipse([x+4, y+14, x+24, y+34], fill=0)
        draw_obj.ellipse([x+20, y+12, x+44, y+34], fill=0)
        draw_obj.rectangle([x+14, y+20, x+36, y+34], fill=0)
        for rx in [x+12, x+22, x+32]:
            draw_obj.line([(rx, y+36), (rx-3, y+44)], fill=0, width=2)

def draw_mini_weather_icon(draw_obj, code, x, y):
    # Compact icon for the 5-day row
    if code in [0, 1]:  # Sun
        draw_obj.ellipse([x+6, y+6, x+22, y+22], fill=0)
        for p1, p2 in [
            ((x+14, y+1), (x+14, y+4)), ((x+14, y+24), (x+14, y+27)),
            ((x+1, y+14), (x+4, y+14)), ((x+24, y+14), (x+27, y+14)),
            ((x+4, y+4), (x+7, y+7)), ((x+21, y+21), (x+24, y+24)),
            ((x+4, y+24), (x+7, y+21)), ((x+21, y+7), (x+24, y+4))
        ]:
            draw_obj.line([p1, p2], fill=0, width=1)
    elif code in [2, 3]:  # Clouds
        draw_obj.ellipse([x+9, y+6, x+23, y+20], fill=0)
        draw_obj.ellipse([x+3, y+11, x+15, y+23], fill=0)
        draw_obj.ellipse([x+13, y+10, x+27, y+23], fill=0)
        draw_obj.rectangle([x+9, y+15, x+22, y+23], fill=0)
    else:  # Rain
        draw_obj.ellipse([x+9, y+4, x+23, y+17], fill=0)
        draw_obj.ellipse([x+3, y+8, x+15, y+20], fill=0)
        draw_obj.ellipse([x+13, y+7, x+27, y+20], fill=0)
        draw_obj.rectangle([x+9, y+12, x+22, y+20], fill=0)
        for rx in [x+8, x+14, x+20]:
            draw_obj.line([(rx, y+22), (rx-2, y+27)], fill=0, width=1)

# --- TOP STATUS BAR ---
draw.rounded_rectangle([(12, 10), (WIDTH - 12, 48)], radius=19, outline=0, width=2)
tz_wa = datetime.timezone(datetime.timedelta(hours=8))
now_wa = datetime.datetime.now(tz_wa)
date_str = now_wa.strftime("%A, %d %B %Y").upper()
time_now_str = now_wa.strftime("%I:%M %p").lstrip('0')
draw.text((28, 20), "BALINGUP DASHBOARD", font=font_title, fill=0)
draw.text((WIDTH - 230, 23), date_str, font=font_small, fill=0)

# --- LEFT COLUMN: AGENDA ---
# Card 1: Today & Tomorrow
draw.rounded_rectangle([(12, 58), (435, 335)], radius=22, outline=0, width=2)

# Section: TODAY
draw.rounded_rectangle([(24, 70), (105, 92)], radius=11, outline=0, width=1)
draw.text((36, 74), "TODAY", font=font_card_head, fill=0)

y_cursor = 100
if today_events:
    for _, t_str, summ in today_events[:4]:
        label = f"• {summ}" if not t_str else f"• {t_str} - {summ}"
        label = label[:38] + "..." if len(label) > 40 else label
        draw.text((28, y_cursor), label, font=font_sub, fill=0)
        y_cursor += 20
else:
    draw.text((28, y_cursor), "• No events today", font=font_sub, fill=0)
    y_cursor += 20

# Section: TOMORROW
y_cursor = max(y_cursor + 6, 185)
draw.rounded_rectangle([(24, y_cursor), (145, y_cursor + 22)], radius=11, outline=0, width=1)
draw.text((36, y_cursor + 4), "TOMORROW", font=font_card_head, fill=0)
y_cursor += 30

if tomorrow_events:
    for _, t_str, summ in tomorrow_events[:4]:
        label = f"• {summ}" if not t_str else f"• {t_str} - {summ}"
        label = label[:38] + "..." if len(label) > 40 else label
        draw.text((28, y_cursor), label, font=font_sub, fill=0)
        y_cursor += 20
else:
    draw.text((28, y_cursor), "• No events tomorrow", font=font_sub, fill=0)

# Card 2: Looking Ahead
draw.rounded_rectangle([(12, 345), (435, 468)], radius=20, outline=0, width=2)
draw.rounded_rectangle([(24, 355), (160, 375)], radius=10, outline=0, width=1)
draw.text((34, 358), "LOOKING AHEAD", font=font_small, fill=0)

y_ahead = 385
if later_events:
    for d, t_str, summ in later_events[:3]:
        day_tag = d.strftime("%a %d")
        ahead_label = f"{day_tag}: {summ}"
        ahead_label = ahead_label[:38] + "..." if len(ahead_label) > 40 else ahead_label
        draw.text((28, y_ahead), ahead_label, font=font_sub, fill=0)
        y_ahead += 22
else:
    draw.text((28, y_ahead), "No upcoming events this week.", font=font_sub, fill=0)

# --- RIGHT COLUMN: WEATHER WIDGETS ---
# Card 3: Weather Station (447, 58) to (WIDTH - 12, 250)
draw.rounded_rectangle([(447, 58), (WIDTH - 12, 250)], radius=22, outline=0, width=2)
draw.rounded_rectangle([(460, 68), (610, 90)], radius=11, outline=0, width=1)
draw.text((472, 72), "WEATHER STATION", font=font_card_head, fill=0)

if ecowitt:
    draw.text((462, 98), f"{ecowitt['temp_c']}°", font=font_hero, fill=0)
    
    # Humidity and Timestamp
    draw.text((605, 102), f"HUMIDITY: {ecowitt['humidity']}%", font=font_sub, fill=0)
    draw.text((605, 120), f"UPDATED {time_now_str}", font=font_small, fill=0)

    # Yesterday's High / Low
    if bom and "yesterday" in bom:
        draw.text((462, 146), f"Yesterday: Max {bom['yesterday']['max']}°C | Min {bom['yesterday']['min']}°C", font=font_small, fill=0)

    # Dotted divider line
    for dx in range(460, WIDTH - 24, 6):
        draw.point((dx, 166), fill=0)

    draw.text((462, 174), f"Rain 24h: {ecowitt['rain_24h']} mm", font=font_sub, fill=0)
    draw.text((605, 174), f"Weekly: {ecowitt['rain_weekly']} mm", font=font_sub, fill=0)
    draw.text((462, 198), f"Last Event: {ecowitt['rain_event']} mm", font=font_sub, fill=0)
    draw.text((605, 198), "(Reset at 9 AM)", font=font_small, fill=0)
else:
    draw.text((462, 110), "Sensors connecting...", font=font_sub, fill=0)

# Card 4: Balingup Weather Forecast BOM (447, 260) to (WIDTH - 12, 468)
draw.rounded_rectangle([(447, 260), (WIDTH - 12, 468)], radius=22, outline=0, width=2)
draw.rounded_rectangle([(460, 270), (745, 292)], radius=11, outline=0, width=1)
draw.text((472, 274), "BALINGUP WEATHER FORECAST BOM", font=font_card_head, fill=0)

if bom:
    # Today's forecast block
    draw_weather_icon(draw, bom["today"]["code"], 458, 302)
    draw.text((514, 302), f"TODAY  Max {bom['today']['max']}° | Min {bom['today']['min']}°", font=font_sub, fill=0)
    draw.text((514, 320), f"Precip: {bom['today']['rain_prob']}% ({bom['today']['rain_sum']} mm)", font=font_small, fill=0)

    # Tomorrow's forecast block
    draw_weather_icon(draw, bom["tomorrow"]["code"], 458, 350)
    draw.text((514, 350), f"TOMORROW  Max {bom['tomorrow']['max']}° | Min {bom['tomorrow']['min']}°", font=font_sub, fill=0)
    draw.text((514, 368), f"Precip: {bom['tomorrow']['rain_prob']}% ({bom['tomorrow']['rain_sum']} mm)", font=font_small, fill=0)

    # Dotted divider line above 5-day strip
    for dx in range(460, WIDTH - 24, 6):
        draw.point((dx, 398), fill=0)

    # 5-Day Strip at the bottom
    col_width = (WIDTH - 24 - 460) // 5
    for i, item in enumerate(bom.get("next_5_days", [])):
        col_x = 460 + (i * col_width)
        center_x = col_x + (col_width // 2)

        # Mini icon centered
        draw_mini_weather_icon(draw, item["code"], center_x - 14, 408)
        
        # Day name centered below symbol
        day_text = item["day_name"]
        draw.text((center_x - 11, 442), day_text, font=font_tiny_bold, fill=0)
else:
    draw.text((460, 310), "Forecast unavailable", font=font_sub, fill=0)

img.save("dashboard.png", "PNG")
log("Saved dashboard with 5-day forecast row successfully!")
