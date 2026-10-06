import os
import requests
import datetime
from dateutil import rrule as drrule
from icalendar import Calendar
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480

def log(msg):
    print(f"LOG: {msg}", flush=True)

# --- COLOR PALETTE (Material You / Android Theme) ---
COLOR_BG = (248, 249, 250)         # Soft porcelain white
COLOR_CARD = (255, 255, 255)       # Card background
COLOR_BORDER = (220, 224, 230)     # Clean hairline borders
COLOR_TEXT_DARK = (28, 30, 33)     # Primary charcoal text
COLOR_TEXT_MUTED = (108, 115, 125) # Secondary grey text
COLOR_ACCENT = (41, 98, 255)       # Primary vibrant blue

# Event Category Accents
COLOR_WORK = (26, 115, 232)        # Blue
COLOR_AIRBNB = (224, 86, 76)       # Coral
COLOR_FAMILY = (30, 142, 62)       # Green
COLOR_HOLIDAY = (227, 116, 0)      # Amber / Orange

# Weather Art Colors
COLOR_SUN = (245, 158, 11)         # Golden amber
COLOR_CLOUD_LIGHT = (203, 213, 225)# Slate cloud fill
COLOR_CLOUD_DARK = (148, 163, 184) # Cloud outline
COLOR_RAIN = (59, 130, 246)        # Water blue

# --- 1. CALENDAR FETCHER WITH AUTO-COLORING ---
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
        is_holiday = "41p9gaols1it9m" in url.lower()

        if is_airbnb:
            category_color = COLOR_AIRBNB
        elif is_holiday:
            category_color = COLOR_HOLIDAY
        elif idx == 0:
            category_color = COLOR_FAMILY
        else:
            category_color = COLOR_WORK

        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code != 200:
                continue

            cal = Calendar.from_ical(res.text)
            for component in cal.walk():
                if component.name == "VEVENT":
                    summary = str(component.get("summary", "Untitled"))
                    if is_airbnb and "reserved" in summary.lower():
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

                    event_color = category_color
                    if "work" in summary.lower():
                        event_color = COLOR_WORK

                    for d in set(active_dates):
                        if today <= d <= future_cutoff:
                            raw_events.append((d, time_str, summary, event_color))

        except Exception as e:
            log(f"Feed error: {e}")

    unique = list({(e[0], e[1], e[2]): e for e in raw_events}.values())
    unique.sort(key=lambda x: (x[0], 0 if x[1] == "" else 1, x[1]))

    today_events = [e for e in unique if e[0] == today]
    tomorrow_events = [e for e in unique if e[0] == tomorrow]
    later_events = [e for e in unique if e[0] > tomorrow]

    return today_events, tomorrow_events, later_events

# --- 2. ECOWITT SENSOR FETCHER ---
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
        temp_data = outdoor.get("temperature", {})

        def parse_temp(val_item):
            if val_item is None:
                return None
            if isinstance(val_item, dict):
                val = float(val_item.get("value", 0))
                unit = val_item.get("unit", "C")
            else:
                val = float(val_item)
                unit = temp_data.get("unit", "C")
            return round((val - 32) * 5 / 9, 1) if "F" in str(unit).upper() else round(val, 1)

        temp_c = parse_temp(temp_data)
        humidity = outdoor.get("humidity", {}).get("value", "--")

        def to_mm(metric_dict):
            if not metric_dict:
                return 0.0
            val = float(metric_dict.get("value", 0.0))
            unit = metric_dict.get("unit", "mm")
            return round(val * 25.4, 1) if "in" in str(unit).lower() else round(val, 1)

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

# --- 3. BOM FORECAST & HOURLY FETCHER ---
def get_balingup_bom():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude=-33.7865&longitude=115.9838&"
        "daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max&"
        "hourly=temperature_2m&"
        "past_days=1&forecast_days=7&"
        "timezone=Australia%2FPerth"
    )
    try:
        res = requests.get(url, timeout=10).json()
        if "daily" not in res:
            log(f"Open-Meteo error: {res}")
            return None

        daily = res["daily"]
        dates = [datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in daily["time"]]

        # Extract true overnight low (yesterday 8 PM to today 8 AM)
        hourly_temps = res.get("hourly", {}).get("temperature_2m", [])
        overnight_slice = hourly_temps[20:33] if len(hourly_temps) >= 33 else []
        overnight_low = round(min(overnight_slice)) if overnight_slice else round(daily["temperature_2m_min"][1])
        yesterday_high = round(daily["temperature_2m_max"][0])

        upcoming_5_days = []
        for i in range(3, min(8, len(dates))):
            upcoming_5_days.append({
                "date": dates[i],
                "day_name": dates[i].strftime("%a").capitalize(),
                "code": daily["weathercode"][i]
            })

        rain_sums = daily.get("precipitation_sum", [0.0]*8)
        rain_probs = daily.get("precipitation_probability_max", [0]*8)

        return {
            "yesterday_high": yesterday_high,
            "overnight_low": overnight_low,
            "today": {
                "code": daily["weathercode"][1],
                "max": round(daily["temperature_2m_max"][1]),
                "min": round(daily["temperature_2m_min"][1]),
                "rain_sum": rain_sums[1] if len(rain_sums) > 1 and rain_sums[1] is not None else 0.0,
                "rain_prob": rain_probs[1] if len(rain_probs) > 1 and rain_probs[1] is not None else 0,
            },
            "tomorrow": {
                "code": daily["weathercode"][2],
                "max": round(daily["temperature_2m_max"][2]),
                "min": round(daily["temperature_2m_min"][2]),
                "rain_sum": rain_sums[2] if len(rain_sums) > 2 and rain_sums[2] is not None else 0.0,
                "rain_prob": rain_probs[2] if len(rain_probs) > 2 and rain_probs[2] is not None else 0,
            },
            "next_5_days": upcoming_5_days
        }
    except Exception as e:
        log(f"BOM error: {e}")
        return None

today_events, tomorrow_events, later_events = get_calendar_events()
ecowitt = get_ecowitt_data()
bom = get_balingup_bom()

# --- 4. RENDER ENGINE (RGB) ---
img = Image.new('RGB', (WIDTH, HEIGHT), COLOR_BG)
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

font_hero = load_font(44)
font_title = load_font(16)
font_card_head = load_font(12)
font_sub = load_font(12)
font_small = load_font(10)
font_tiny = load_font(10)

def draw_color_weather_icon(draw_obj, code, x, y):
    if code in [0, 1]:  # Sun
        draw_obj.ellipse([x+8, y+8, x+36, y+36], fill=COLOR_SUN)
        for p1, p2 in [
            ((x+22, y), (x+22, y+5)), ((x+22, y+39), (x+22, y+44)),
            ((x, y+22), (x+5, y+22)), ((x+39, y+22), (x+44, y+22)),
            ((x+6, y+6), (x+10, y+10)), ((x+34, y+34), (x+38, y+38)),
            ((x+6, y+38), (x+10, y+34)), ((x+34, y+10), (x+38, y+6))
        ]:
            draw_obj.line([p1, p2], fill=COLOR_SUN, width=2)
    elif code in [2, 3]:  # Clouds
        draw_obj.ellipse([x+14, y+10, x+38, y+34], fill=COLOR_CLOUD_LIGHT, outline=COLOR_CLOUD_DARK)
        draw_obj.ellipse([x+4, y+18, x+24, y+38], fill=COLOR_CLOUD_LIGHT, outline=COLOR_CLOUD_DARK)
        draw_obj.ellipse([x+20, y+16, x+44, y+38], fill=COLOR_CLOUD_LIGHT, outline=COLOR_CLOUD_DARK)
        draw_obj.rectangle([x+14, y+24, x+36, y+38], fill=COLOR_CLOUD_LIGHT)
    else:  # Rain
        draw_obj.ellipse([x+14, y+6, x+38, y+30], fill=COLOR_CLOUD_LIGHT, outline=COLOR_CLOUD_DARK)
        draw_obj.ellipse([x+4, y+14, x+24, y+34], fill=COLOR_CLOUD_LIGHT, outline=COLOR_CLOUD_DARK)
        draw_obj.ellipse([x+20, y+12, x+44, y+34], fill=COLOR_CLOUD_LIGHT, outline=COLOR_CLOUD_DARK)
        draw_obj.rectangle([x+14, y+20, x+36, y+34], fill=COLOR_CLOUD_LIGHT)
        for rx in [x+12, x+22, x+32]:
            draw_obj.line([(rx, y+36), (rx-3, y+44)], fill=COLOR_RAIN, width=2)

def draw_mini_color_icon(draw_obj, code, x, y):
    if code in [0, 1]:  # Sun
        draw_obj.ellipse([x+6, y+6, x+22, y+22], fill=COLOR_SUN)
    elif code in [2, 3]:  # Clouds
        draw_obj.ellipse([x+8, y+8, x+22, y+22], fill=COLOR_CLOUD_LIGHT, outline=COLOR_CLOUD_DARK)
        draw_obj.ellipse([x+2, y+12, x+14, y+24], fill=COLOR_CLOUD_LIGHT, outline=COLOR_CLOUD_DARK)
        draw_obj.rectangle([x+6, y+16, x+18, y+24], fill=COLOR_CLOUD_LIGHT)
    else:  # Rain
        draw_obj.ellipse([x+6, y+4, x+20, y+18], fill=COLOR_CLOUD_LIGHT, outline=COLOR_CLOUD_DARK)
        for rx in [x+8, x+14, x+20]:
            draw_obj.line([(rx, y+20), (rx-2, y+25)], fill=COLOR_RAIN, width=1)

# --- TOP STATUS BAR (HEADER) ---
draw.rounded_rectangle([(12, 10), (WIDTH - 12, 48)], radius=19, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)
tz_wa = datetime.timezone(datetime.timedelta(hours=8))
now_wa = datetime.datetime.now(tz_wa)

date_title_str = now_wa.strftime("%A, %d %B %Y")
time_now_str = now_wa.strftime("%I:%M %p").lstrip('0')
draw.text((28, 20), date_title_str, font=font_title, fill=COLOR_TEXT_DARK)
draw.text((WIDTH - 170, 23), f"Updated {time_now_str}", font=font_small, fill=COLOR_TEXT_MUTED)

# --- LEFT COLUMN: AGENDA ---
# Card 1: Today & Tomorrow
draw.rounded_rectangle([(12, 58), (435, 335)], radius=22, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)

# Section: Today
draw.rounded_rectangle([(24, 70), (105, 92)], radius=11, fill=COLOR_BG, outline=COLOR_BORDER, width=1)
draw.text((38, 74), "Today", font=font_card_head, fill=COLOR_TEXT_DARK)

y_cursor = 100
if today_events:
    for _, t_str, summ, ev_color in today_events[:4]:
        draw.ellipse([28, y_cursor + 4, 34, y_cursor + 10], fill=ev_color)
        label = summ if not t_str else f"{t_str} - {summ}"
        label = label[:36] + "..." if len(label) > 38 else label
        draw.text((42, y_cursor), label, font=font_sub, fill=COLOR_TEXT_DARK)
        y_cursor += 20
else:
    draw.text((28, y_cursor), "No events scheduled today", font=font_sub, fill=COLOR_TEXT_MUTED)
    y_cursor += 20

# Section: Tomorrow
y_cursor = max(y_cursor + 6, 185)
draw.rounded_rectangle([(24, y_cursor), (135, y_cursor + 22)], radius=11, fill=COLOR_BG, outline=COLOR_BORDER, width=1)
draw.text((36, y_cursor + 4), "Tomorrow", font=font_card_head, fill=COLOR_TEXT_DARK)
y_cursor += 30

if tomorrow_events:
    for _, t_str, summ, ev_color in tomorrow_events[:4]:
        draw.ellipse([28, y_cursor + 4, 34, y_cursor + 10], fill=ev_color)
        label = summ if not t_str else f"{t_str} - {summ}"
        label = label[:36] + "..." if len(label) > 38 else label
        draw.text((42, y_cursor), label, font=font_sub, fill=COLOR_TEXT_DARK)
        y_cursor += 20
else:
    draw.text((28, y_cursor), "No events scheduled tomorrow", font=font_sub, fill=COLOR_TEXT_MUTED)

# Card 2: Looking Ahead
draw.rounded_rectangle([(12, 345), (435, 468)], radius=20, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)
draw.rounded_rectangle([(24, 355), (150, 375)], radius=10, fill=COLOR_BG, outline=COLOR_BORDER, width=1)
draw.text((34, 358), "Looking Ahead", font=font_small, fill=COLOR_TEXT_DARK)

y_ahead = 385
if later_events:
    for d, t_str, summ, ev_color in later_events[:3]:
        day_tag = d.strftime("%a %d")
        draw.ellipse([28, y_ahead + 4, 34, y_ahead + 10], fill=ev_color)
        ahead_label = f"{day_tag}: {summ}"
        ahead_label = ahead_label[:36] + "..." if len(ahead_label) > 38 else ahead_label
        draw.text((42, y_ahead), ahead_label, font=font_sub, fill=COLOR_TEXT_DARK)
        y_ahead += 22
else:
    draw.text((28, y_ahead), "No upcoming events this week.", font=font_sub, fill=COLOR_TEXT_MUTED)

# --- RIGHT COLUMN: WEATHER WIDGETS ---
# Card 3: Weather Station
draw.rounded_rectangle([(447, 58), (WIDTH - 12, 250)], radius=22, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)
draw.rounded_rectangle([(460, 68), (595, 90)], radius=11, fill=COLOR_BG, outline=COLOR_BORDER, width=1)
draw.text((472, 72), "Weather Station", font=font_card_head, fill=COLOR_TEXT_DARK)

if ecowitt:
    draw.text((462, 98), f"{ecowitt['temp_c']}°", font=font_hero, fill=COLOR_TEXT_DARK)
    draw.text((605, 110), f"Humidity: {ecowitt['humidity']}%", font=font_sub, fill=COLOR_TEXT_DARK)

    # Show: Yesterday's High : X°C  |  Overnight's Low : Y°C
    if bom and "yesterday_high" in bom and "overnight_low" in bom:
        stat_line = f"Yesterday's High : {bom['yesterday_high']}°C  |  Overnight's Low : {bom['overnight_low']}°C"
        draw.text((462, 146), stat_line, font=font_small, fill=COLOR_TEXT_MUTED)

    for dx in range(460, WIDTH - 24, 6):
        draw.point((dx, 166), fill=COLOR_BORDER)

    draw.text((462, 174), f"Rain 24h: {ecowitt['rain_24h']} mm", font=font_sub, fill=COLOR_TEXT_DARK)
    draw.text((605, 174), f"Weekly: {ecowitt['rain_weekly']} mm", font=font_sub, fill=COLOR_TEXT_DARK)
    draw.text((462, 198), f"Last Event: {ecowitt['rain_event']} mm", font=font_sub, fill=COLOR_TEXT_DARK)
    draw.text((605, 198), "(Reset at 9 AM)", font=font_small, fill=COLOR_TEXT_MUTED)
else:
    draw.text((462, 110), "Sensors connecting...", font=font_sub, fill=COLOR_TEXT_MUTED)

# Card 4: Balingup Weather Forecast
draw.rounded_rectangle([(447, 260), (WIDTH - 12, 468)], radius=22, fill=COLOR_CARD, outline=COLOR_BORDER, width=1)
draw.rounded_rectangle([(460, 270), (700, 292)], radius=11, fill=COLOR_BG, outline=COLOR_BORDER, width=1)
draw.text((472, 274), "Balingup Weather Forecast", font=font_card_head, fill=COLOR_TEXT_DARK)

if bom:
    draw_color_weather_icon(draw, bom["today"]["code"], 458, 302)
    draw.text((514, 302), f"Today  Max {bom['today']['max']}° | Min {bom['today']['min']}°", font=font_sub, fill=COLOR_TEXT_DARK)
    draw.text((514, 320), f"Precip: {bom['today']['rain_prob']}% ({bom['today']['rain_sum']} mm)", font=font_small, fill=COLOR_TEXT_MUTED)

    draw_color_weather_icon(draw, bom["tomorrow"]["code"], 458, 350)
    draw.text((514, 350), f"Tomorrow  Max {bom['tomorrow']['max']}° | Min {bom['tomorrow']['min']}°", font=font_sub, fill=COLOR_TEXT_DARK)
    draw.text((514, 368), f"Precip: {bom['tomorrow']['rain_prob']}% ({bom['tomorrow']['rain_sum']} mm)", font=font_small, fill=COLOR_TEXT_MUTED)

    for dx in range(460, WIDTH - 24, 6):
        draw.point((dx, 398), fill=COLOR_BORDER)

    col_width = (WIDTH - 24 - 460) // 5
    for i, item in enumerate(bom.get("next_5_days", [])):
        col_x = 460 + (i * col_width)
        center_x = col_x + (col_width // 2)

        draw_mini_color_icon(draw, item["code"], center_x - 14, 408)
        day_text = item["day_name"]
        draw.text((center_x - 12, 442), day_text, font=font_tiny, fill=COLOR_TEXT_DARK)
else:
    draw.text((460, 310), "Forecast unavailable", font=font_sub, fill=COLOR_TEXT_MUTED)

img.save("dashboard.png", "PNG")
log("Saved complete dashboard successfully!")
