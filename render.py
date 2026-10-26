import os
import requests
import datetime
from dateutil import rrule as drrule
from icalendar import Calendar
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480

def log(msg):
    print(f"LOG: {msg}", flush=True)

# --- HIGH-CONTRAST ACeP E-PAPER COLOR PALETTE ---
# Pure solids eliminate dithering, fuzzy text, and missing borders
COLOR_BG = (255, 255, 255)         # Pure paper white
COLOR_CARD = (255, 255, 255)       # Pure card white
COLOR_BORDER = (70, 75, 85)        # Solid, high-contrast dark border
COLOR_BORDER_THIN = (140, 145, 155)# Secondary divider border
COLOR_TEXT_DARK = (0, 0, 0)        # Pure pitch black for razor-sharp characters
COLOR_TEXT_MUTED = (40, 45, 50)    # Dark charcoal for secondary readouts
COLOR_PILL_BG = (235, 238, 245)    # Light gray tint for section badges
COLOR_PILL_DARK = (45, 52, 64)     # Inverted badge fill for crisp readability

# Event Accents (Saturated e-paper native pigments)
COLOR_WORK = (0, 75, 195)          # Solid royal blue
COLOR_AIRBNB = (220, 20, 60)       # Solid crimson red
COLOR_FAMILY = (0, 140, 60)        # Forest green
COLOR_HOLIDAY = (210, 100, 0)      # Rich amber/orange

# Weather & Sky Palette
COLOR_SUN = (245, 160, 0)          # Solar yellow-orange
COLOR_SUN_RAY = (210, 110, 0)      # Saturated orange rays
COLOR_CLOUD = (180, 195, 210)      # Visible sky-slate cloud body
COLOR_CLOUD_BORDER = (40, 50, 70)  # Dark cloud perimeter
COLOR_RAIN = (0, 95, 220)          # Deep rain blue
COLOR_ACCENT_ORANGE = (220, 75, 0)

# --- 1. CALENDAR FETCHER ---
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

                    effective_end = base_end_date - datetime.timedelta(days=1) if (is_all_day and base_end_date > base_start_date) else base_end_date

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

# --- 3. OPEN-METEO WEATHER & SOLAR FETCHER ---
def get_balingup_bom():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude=-33.7865&longitude=115.9838&"
        "daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,sunrise,sunset&"
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

        hourly_temps = res.get("hourly", {}).get("temperature_2m", [])
        overnight_slice = hourly_temps[20:33] if len(hourly_temps) >= 33 else []
        overnight_low = round(min(overnight_slice)) if overnight_slice else round(daily["temperature_2m_min"][1])
        yesterday_high = round(daily["temperature_2m_max"][0])

        def format_solar_time(iso_str, delta_minutes=0):
            if not iso_str:
                return "--:--"
            dt = datetime.datetime.fromisoformat(iso_str) + datetime.timedelta(minutes=delta_minutes)
            return dt.strftime("%I:%M %p").lstrip('0')

        today_sunrise_iso = daily["sunrise"][1] if len(daily.get("sunrise", [])) > 1 else None
        today_sunset_iso = daily["sunset"][1] if len(daily.get("sunset", [])) > 1 else None

        sunrise_str = format_solar_time(today_sunrise_iso)
        sunset_str = format_solar_time(today_sunset_iso)
        first_light_str = format_solar_time(today_sunrise_iso, -26)
        last_light_str = format_solar_time(today_sunset_iso, 26)

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
            "today_date": dates[1],
            "first_light": first_light_str,
            "sunrise": sunrise_str,
            "sunset": sunset_str,
            "last_light": last_light_str,
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

# --- 4. RENDER ENGINE & FONT SELECTION ---
img = Image.new('RGB', (WIDTH, HEIGHT), COLOR_BG)
draw = ImageDraw.Draw(img)

def load_font(size, bold=True):
    font_candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "DejaVuSans.ttf"
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

# Bumped font sizes and increased weights to eliminate e-paper blurriness
font_hero = load_font(44, bold=True)
font_title = load_font(18, bold=True)
font_card_head = load_font(13, bold=True)
font_body = load_font(14, bold=False)
font_body_bold = load_font(14, bold=True)
font_small = load_font(12, bold=True)
font_tiny = load_font(11, bold=True)

# --- 5. HIGH-CONTRAST WEATHER ART ENGINE ---
def draw_little_bird(draw_obj, bx, by, color=COLOR_TEXT_DARK):
    draw_obj.arc([bx, by, bx + 8, by + 6], 180, 0, fill=color, width=2)
    draw_obj.arc([bx + 7, by, bx + 15, by + 6], 180, 0, fill=color, width=2)

def draw_homely_weather_art(draw_obj, code, x, y):
    if code in [0, 1]:  # Sunny / Clear
        # Pure solar sphere with solid ray accents
        draw_obj.ellipse([x + 6, y + 6, x + 36, y + 36], fill=COLOR_SUN, outline=COLOR_SUN_RAY, width=2)
        for dx, dy in [(-6, 0), (6, 0), (0, -6), (0, 6), (-4, -4), (4, -4), (-4, 4), (4, 4)]:
            cx, cy = x + 21 + dx * 2.8, y + 21 + dy * 2.8
            draw_obj.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=COLOR_SUN_RAY)
        draw_little_bird(draw_obj, x + 28, y + 2)

    elif code in [2, 3]:  # Cloudy / Overcast
        draw_obj.ellipse([x + 12, y + 8, x + 38, y + 32], fill=COLOR_CLOUD, outline=COLOR_CLOUD_BORDER, width=2)
        draw_obj.ellipse([x + 2, y + 16, x + 24, y + 36], fill=COLOR_CLOUD, outline=COLOR_CLOUD_BORDER, width=2)
        draw_obj.ellipse([x + 18, y + 14, x + 44, y + 36], fill=COLOR_CLOUD, outline=COLOR_CLOUD_BORDER, width=2)
        draw_obj.rectangle([x + 12, y + 20, x + 36, y + 36], fill=COLOR_CLOUD)
        draw_obj.line([(x + 2, y + 36), (x + 44, y + 36)], fill=COLOR_CLOUD_BORDER, width=2)

    else:  # Rain / Showers
        draw_obj.ellipse([x + 12, y + 6, x + 38, y + 28], fill=COLOR_CLOUD, outline=COLOR_CLOUD_BORDER, width=2)
        draw_obj.ellipse([x + 2, y + 12, x + 24, y + 32], fill=COLOR_CLOUD, outline=COLOR_CLOUD_BORDER, width=2)
        draw_obj.ellipse([x + 18, y + 10, x + 44, y + 32], fill=COLOR_CLOUD, outline=COLOR_CLOUD_BORDER, width=2)
        draw_obj.rectangle([x + 12, y + 16, x + 36, y + 32], fill=COLOR_CLOUD)
        draw_obj.line([(x + 2, y + 32), (x + 44, y + 32)], fill=COLOR_CLOUD_BORDER, width=2)

        # Bold saturated rain streaks
        for rx in [x + 9, x + 18, x + 27, x + 36]:
            draw_obj.line([(rx, y + 35), (rx - 3, y + 43)], fill=COLOR_RAIN, width=3)

def draw_mini_icon(draw_obj, code, x, y):
    if code in [0, 1]:
        draw_obj.ellipse([x + 3, y + 3, x + 21, y + 21], fill=COLOR_SUN, outline=COLOR_SUN_RAY, width=2)
    elif code in [2, 3]:
        draw_obj.ellipse([x + 7, y + 4, x + 21, y + 18], fill=COLOR_CLOUD, outline=COLOR_CLOUD_BORDER, width=2)
        draw_obj.ellipse([x + 1, y + 8, x + 13, y + 20], fill=COLOR_CLOUD, outline=COLOR_CLOUD_BORDER, width=2)
        draw_obj.rectangle([x + 5, y + 12, x + 17, y + 20], fill=COLOR_CLOUD)
        draw_obj.line([(x + 1, y + 20), (x + 21, y + 20)], fill=COLOR_CLOUD_BORDER, width=2)
    else:
        draw_obj.ellipse([x + 4, y + 2, x + 18, y + 15], fill=COLOR_CLOUD, outline=COLOR_CLOUD_BORDER, width=2)
        draw_obj.line([(x + 2, y + 15), (x + 20, y + 15)], fill=COLOR_CLOUD_BORDER, width=2)
        for rx in [x + 6, x + 12, x + 18]:
            draw_obj.line([(rx, y + 17), (rx - 2, y + 23)], fill=COLOR_RAIN, width=2)

# --- HEADER BAR ---
draw.rounded_rectangle([(12, 10), (WIDTH - 12, 48)], radius=14, fill=COLOR_CARD, outline=COLOR_BORDER, width=2)
tz_wa = datetime.timezone(datetime.timedelta(hours=8))
now_wa = datetime.datetime.now(tz_wa)

date_title_str = now_wa.strftime("%A, %d %B %Y")
time_now_str = now_wa.strftime("%I:%M %p").lstrip('0')
draw.text((26, 17), date_title_str, font=font_title, fill=COLOR_TEXT_DARK)
draw.text((WIDTH - 150, 21), f"Updated {time_now_str}", font=font_small, fill=COLOR_TEXT_DARK)

# --- LEFT COLUMN: AGENDA ---
# Card 1: Today & Tomorrow
draw.rounded_rectangle([(12, 58), (435, 335)], radius=16, fill=COLOR_CARD, outline=COLOR_BORDER, width=2)

# Section: Today
draw.rounded_rectangle([(24, 68), (110, 92)], radius=8, fill=COLOR_PILL_DARK)
draw.text((38, 72), "Today", font=font_card_head, fill=(255, 255, 255))

y_cursor = 102
if today_events:
    for _, t_str, summ, ev_color in today_events[:4]:
        draw.ellipse([26, y_cursor + 3, 34, y_cursor + 11], fill=ev_color)
        label = summ if not t_str else f"{t_str} - {summ}"
        label = label[:34] + "..." if len(label) > 36 else label
        draw.text((42, y_cursor), label, font=font_body, fill=COLOR_TEXT_DARK)
        y_cursor += 22
else:
    draw.text((28, y_cursor), "No events scheduled today", font=font_body, fill=COLOR_TEXT_MUTED)
    y_cursor += 22

# Section: Tomorrow
y_cursor = max(y_cursor + 8, 192)
draw.rounded_rectangle([(24, y_cursor), (135, y_cursor + 24)], radius=8, fill=COLOR_PILL_DARK)
draw.text((38, y_cursor + 4), "Tomorrow", font=font_card_head, fill=(255, 255, 255))
y_cursor += 32

if tomorrow_events:
    for _, t_str, summ, ev_color in tomorrow_events[:4]:
        draw.ellipse([26, y_cursor + 3, 34, y_cursor + 11], fill=ev_color)
        label = summ if not t_str else f"{t_str} - {summ}"
        label = label[:34] + "..." if len(label) > 36 else label
        draw.text((42, y_cursor), label, font=font_body, fill=COLOR_TEXT_DARK)
        y_cursor += 22
else:
    draw.text((28, y_cursor), "No events scheduled tomorrow", font=font_body, fill=COLOR_TEXT_MUTED)

# Card 2: Looking Ahead
draw.rounded_rectangle([(12, 345), (435, 468)], radius=16, fill=COLOR_CARD, outline=COLOR_BORDER, width=2)
draw.rounded_rectangle([(24, 355), (155, 377)], radius=8, fill=COLOR_PILL_DARK)
draw.text((36, 359), "Looking Ahead", font=font_card_head, fill=(255, 255, 255))

y_ahead = 388
if later_events:
    for d, t_str, summ, ev_color in later_events[:3]:
        day_tag = d.strftime("%a %d")
        draw.ellipse([26, y_ahead + 3, 34, y_ahead + 11], fill=ev_color)
        ahead_label = f"{day_tag}: {summ}"
        ahead_label = ahead_label[:34] + "..." if len(ahead_label) > 36 else ahead_label
        draw.text((42, y_ahead), ahead_label, font=font_body, fill=COLOR_TEXT_DARK)
        y_ahead += 23
else:
    draw.text((28, y_ahead), "No upcoming events this week.", font=font_body, fill=COLOR_TEXT_MUTED)

# --- RIGHT COLUMN: WEATHER WIDGETS ---
# Card 3: Weather Station
draw.rounded_rectangle([(447, 58), (WIDTH - 12, 235)], radius=16, fill=COLOR_CARD, outline=COLOR_BORDER, width=2)
draw.rounded_rectangle([(460, 68), (595, 92)], radius=8, fill=COLOR_PILL_DARK)
draw.text((472, 72), "Weather Station", font=font_card_head, fill=(255, 255, 255))

if ecowitt:
    draw.text((462, 96), f"{ecowitt['temp_c']}°", font=font_hero, fill=COLOR_TEXT_DARK)
    draw.text((605, 108), f"Humidity: {ecowitt['humidity']}%", font=font_body_bold, fill=COLOR_TEXT_DARK)

    if bom and "yesterday_high" in bom and "overnight_low" in bom:
        today_date_str = bom.get("today_date", now_wa.date()).strftime("%d %b")
        stat_line = f"Yesterday High: {bom['yesterday_high']}°C  |  Low: {bom['overnight_low']}°C"
        draw.text((462, 146), stat_line, font=font_small, fill=COLOR_TEXT_DARK)

    # Solid 2px divider line instead of weak dots
    draw.line([(462, 166), (WIDTH - 24, 166)], fill=COLOR_BORDER_THIN, width=2)

    draw.text((462, 174), f"Rain 24h: {ecowitt['rain_24h']} mm", font=font_body_bold, fill=COLOR_TEXT_DARK)
    draw.text((615, 174), f"Weekly: {ecowitt['rain_weekly']} mm", font=font_body_bold, fill=COLOR_TEXT_DARK)
    draw.text((462, 198), f"Last Event: {ecowitt['rain_event']} mm", font=font_body, fill=COLOR_TEXT_DARK)
    draw.text((615, 198), "(Reset at 9 AM)", font=font_small, fill=COLOR_TEXT_MUTED)
else:
    draw.text((462, 110), "Sensors connecting...", font=font_body, fill=COLOR_TEXT_MUTED)

# Card 4: Balingup Forecast & Solar Times
draw.rounded_rectangle([(447, 245), (WIDTH - 12, 468)], radius=16, fill=COLOR_CARD, outline=COLOR_BORDER, width=2)
draw.rounded_rectangle([(460, 255), (690, 279)], radius=8, fill=COLOR_PILL_DARK)
draw.text((472, 259), "Balingup Weather Forecast", font=font_card_head, fill=(255, 255, 255))

if bom:
    # Today Forecast Item
    draw_homely_weather_art(draw, bom["today"]["code"], 458, 286)
    draw.text((514, 288), f"Today  Max {bom['today']['max']}° | Min {bom['today']['min']}°", font=font_body_bold, fill=COLOR_TEXT_DARK)
    draw.text((514, 308), f"Precip: {bom['today']['rain_prob']}% ({bom['today']['rain_sum']} mm)", font=font_small, fill=COLOR_TEXT_MUTED)

    # Tomorrow Forecast Item
    draw_homely_weather_art(draw, bom["tomorrow"]["code"], 458, 332)
    draw.text((514, 334), f"Tomorrow  Max {bom['tomorrow']['max']}° | Min {bom['tomorrow']['min']}°", font=font_body_bold, fill=COLOR_TEXT_DARK)
    draw.text((514, 354), f"Precip: {bom['tomorrow']['rain_prob']}% ({bom['tomorrow']['rain_sum']} mm)", font=font_small, fill=COLOR_TEXT_MUTED)

    # Solar Strip Banner: High-contrast bordered card with dark text
    solar_pill_box = [(458, 376), (WIDTH - 24, 404)]
    draw.rounded_rectangle(solar_pill_box, radius=8, fill=COLOR_PILL_BG, outline=COLOR_BORDER, width=2)

    solar_summary = f"Dawn {bom['first_light']}  •  Rise {bom['sunrise']}  •  Set {bom['sunset']}  •  Dusk {bom['last_light']}"
    draw.text((466, 383), solar_summary, font=font_tiny, fill=COLOR_TEXT_DARK)

    # Mini 5-Day Strip
    col_width = (WIDTH - 24 - 460) // 5
    for i, item in enumerate(bom.get("next_5_days", [])):
        col_x = 460 + (i * col_width)
        center_x = col_x + (col_width // 2)

        draw_mini_icon(draw, item["code"], center_x - 12, 410)
        day_text = item["day_name"]
        draw.text((center_x - 11, 438), day_text, font=font_tiny, fill=COLOR_TEXT_DARK)
else:
    draw.text((460, 310), "Forecast unavailable", font=font_body, fill=COLOR_TEXT_MUTED)

img.save("dashboard.png", "PNG")
log("Saved complete dashboard successfully!")
