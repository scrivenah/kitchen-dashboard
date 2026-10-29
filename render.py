import os
import requests
import datetime
from dateutil import rrule as drrule
from icalendar import Calendar
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

# --- ZERO-DITHER RENDERING ENGINE ---
def draw_sharp_text(base_img, xy, text, font, color):
    """Draws text using a 1-bit hard threshold mask to completely eliminate fuzzy dithering."""
    # Create an invisible black canvas
    mask = Image.new('L', base_img.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    
    # Draw the text in white
    mask_draw.text(xy, text, font=font, fill=255)
    
    # Hard threshold: Convert any soft anti-aliased gray pixels into pure white or pure black
    mask = mask.point(lambda p: 255 if p > 127 else 0, mode='1')
    
    # Create a solid block of our target e-paper color
    color_block = Image.new('RGB', base_img.size, color)
    
    # Stamp the color block onto the main image using our sharp stencil
    base_img.paste(color_block, (0, 0), mask)

# --- 1. CALENDAR FETCHER (WITH COLOR CODING) ---
def get_calendar_events():
    ics_urls = os.environ.get("CALENDAR_ICS_URLS", "")
    if not ics_urls: return [], [], []

    tz_wa = datetime.timezone(datetime.timedelta(hours=8))
    now_wa = datetime.datetime.now(tz_wa)
    today = now_wa.date()
    tomorrow = today + datetime.timedelta(days=1)
    future_cutoff = today + datetime.timedelta(days=6)

    url_list = [u.strip() for u in ics_urls.split(",") if u.strip()]
    raw_events = []

    for url in url_list:
        is_airbnb = "airbnb" in url.lower()
        is_holiday = "41p9gaols1it9m" in url.lower()
        
        # Color coding events based on feed
        if is_airbnb:
            event_color = C_RED
        elif is_holiday:
            event_color = C_ORANGE
        else:
            event_color = C_BLUE

        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
            if res.status_code != 200: continue
            
            cal = Calendar.from_ical(res.text)
            for component in cal.walk():
                if component.name == "VEVENT":
                    summary = str(component.get("summary", "Untitled"))
                    if is_airbnb and "reserved" in summary.lower():
                        summary = "Vic's Shack Reserved"

                    dtstart_prop = component.get("dtstart")
                    if not dtstart_prop: continue
                    
                    dtstart = dtstart_prop.dt
                    dtend_prop = component.get("dtend")
                    dtend = dtend_prop.dt if dtend_prop else dtstart

                    is_all_day = not isinstance(dtstart, datetime.datetime)
                    if not is_all_day:
                        dtstart_local = dtstart.astimezone(tz_wa)
                        dtend_local = dtend.astimezone(tz_wa) if isinstance(dtend, datetime.datetime) else dtstart_local
                        base_start = dtstart_local.date()
                        base_end = dtend_local.date()
                        time_str = dtstart_local.strftime("%I:%M %p").lstrip('0')
                        duration = dtend_local - dtstart_local
                    else:
                        base_start = dtstart
                        base_end = dtend if isinstance(dtend, datetime.date) else dtstart
                        time_str = ""
                        duration = base_end - base_start

                    effective_end = base_end - datetime.timedelta(days=1) if (is_all_day and base_end > base_start) else base_end
                    
                    active_dates = []
                    curr = base_start
                    while curr <= effective_end:
                        active_dates.append(curr)
                        curr += datetime.timedelta(days=1)

                    rrule_prop = component.get("rrule")
                    if rrule_prop:
                        try:
                            rule_str = rrule_prop.to_ical().decode("utf-8")
                            rule_start = dtstart if isinstance(dtstart, datetime.datetime) else datetime.datetime.combine(base_start, datetime.time.min)
                            parsed_rule = drrule.rrulestr(rule_str, dtstart=rule_start)
                            check_start = datetime.datetime.combine(today - datetime.timedelta(days=7), datetime.time.min)
                            check_end = datetime.datetime.combine(future_cutoff + datetime.timedelta(days=1), datetime.time.max)
                            for occ in parsed_rule.between(check_start, check_end, inc=True):
                                occ_end_date = (occ + duration).date() if not is_all_day else (occ.date() + duration - datetime.timedelta(days=1 if duration.days > 0 else 0))
                                occ_curr = occ.date()
                                while occ_curr <= occ_end_date:
                                    active_dates.append(occ_curr)
                                    occ_curr += datetime.timedelta(days=1)
                        except: pass

                    for d in set(active_dates):
                        if today <= d <= future_cutoff:
                            raw_events.append((d, time_str, summary, event_color))
        except Exception as e:
            log(f"Feed error: {e}")

    unique = list({(e[0], e[1], e[2]): e for e in raw_events}.values())
    unique.sort(key=lambda x: (x[0], 0 if x[1] == "" else 1, x[1]))
    return [e for e in unique if e[0] == today], [e for e in unique if e[0] == tomorrow], [e for e in unique if e[0] > tomorrow]

# --- 2. ECOWITT SENSOR FETCHER ---
def get_ecowitt_data():
    app_key = os.environ.get("ECOWITT_APPLICATION_KEY")
    api_key = os.environ.get("ECOWITT_API_KEY")
    mac = os.environ.get("ECOWITT_MAC")
    if not all([app_key, api_key, mac]): return None

    url = f"https://api.ecowitt.net/api/v3/device/real_time?application_key={app_key}&api_key={api_key}&mac={mac}&call_back=outdoor,rainfall"
    try:
        res = requests.get(url, timeout=10).json()
        outdoor = res.get("data", {}).get("outdoor", {})
        rainfall = res.get("data", {}).get("rainfall", {})
        temp = outdoor.get("temperature", {}).get("value", 0)
        return {
            "temp_c": round((float(temp) - 32) * 5 / 9, 1) if "F" in str(outdoor.get("temperature", {}).get("unit", "C")).upper() else round(float(temp), 1),
            "humidity": outdoor.get("humidity", {}).get("value", "--"),
            "rain_24h": round(float(rainfall.get("daily", {}).get("value", 0.0)), 1),
            "rain_weekly": round(float(rainfall.get("weekly", {}).get("value", 0.0)), 1)
        }
    except: return None

# --- 3. OPEN-METEO WEATHER & SOLAR FETCHER ---
def get_balingup_bom():
    url = "https://api.open-meteo.com/v1/forecast?latitude=-33.7865&longitude=115.9838&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,sunrise,sunset&hourly=temperature_2m&past_days=1&forecast_days=7&timezone=Australia%2FPerth"
    try:
        res = requests.get(url, timeout=10).json()
        daily = res["daily"]
        dates = [datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in daily["time"]]
        
        def fmt_time(iso, delta=0):
            if not iso: return "--:--"
            return (datetime.datetime.fromisoformat(iso) + datetime.timedelta(minutes=delta)).strftime("%I:%M %p").lstrip('0')

        return {
            "yesterday_high": round(daily["temperature_2m_max"][0]),
            "overnight_low": round(daily["temperature_2m_min"][1]),
            "today_date": dates[1],
            "first_light": fmt_time(daily["sunrise"][1], -26),
            "sunrise": fmt_time(daily["sunrise"][1]),
            "sunset": fmt_time(daily["sunset"][1]),
            "last_light": fmt_time(daily["sunset"][1], 26),
            "today": {
                "code": daily["weathercode"][1],
                "max": round(daily["temperature_2m_max"][1]),
                "min": round(daily["temperature_2m_min"][1]),
                "rain_prob": daily.get("precipitation_probability_max", [0]*8)[1] or 0,
            },
            "tomorrow": {
                "code": daily["weathercode"][2],
                "max": round(daily["temperature_2m_max"][2]),
                "min": round(daily["temperature_2m_min"][2]),
                "rain_prob": daily.get("precipitation_probability_max", [0]*8)[2] or 0,
            },
            "next_5_days": [{"day_name": dates[i].strftime("%a").capitalize(), "code": daily["weathercode"][i]} for i in range(3, min(8, len(dates)))]
        }
    except: return None

# --- 4. ASSET LOADERS (FONTS & VECTOR MAPPING) ---
def get_weather_icon(wmo_code):
    # Maps BOM numeric codes to weather-icons unicode characters and 7-color e-paper colors
    if wmo_code in [0, 1]: return ("\uf00d", C_YELLOW) # Sunny
    elif wmo_code in [2, 3]: return ("\uf013", C_BLACK) # Cloudy
    elif wmo_code in [45, 48]: return ("\uf014", C_BLACK) # Fog
    elif wmo_code in [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82]: return ("\uf019", C_BLUE) # Rain
    elif wmo_code in [71, 73, 75, 77, 85, 86]: return ("\uf01b", C_BLUE) # Snow/Hail
    elif wmo_code in [95, 96, 99]: return ("\uf01e", C_RED) # Thunderstorm
    return ("\uf00d", C_YELLOW)

def get_moon_phase_name(date_obj):
    new_moon = datetime.date(2000, 1, 6)
    phase_ratio = ((date_obj - new_moon).days % 29.53058867) / 29.53058867
    if phase_ratio < 0.03 or phase_ratio > 0.97: return 'New Moon'
    elif phase_ratio < 0.22: return 'Waxing Crescent'
    elif phase_ratio < 0.28: return 'First Quarter'
    elif phase_ratio < 0.47: return 'Waxing Gibbous'
    elif phase_ratio < 0.53: return 'Full Moon'
    elif phase_ratio < 0.72: return 'Waning Gibbous'
    elif phase_ratio < 0.78: return 'Last Quarter'
    else: return 'Waning Crescent'

def load_font(filename, size):
    try: return ImageFont.truetype(f"font/{filename}", size)
    except: return ImageFont.load_default()

font_hero       = load_font("Amazon Ember Bold.ttf", 44)
font_title      = load_font("Amazon Ember Bold.ttf", 18)
font_card_head  = load_font("Amazon Ember Bold.ttf", 15)
font_body       = load_font("Amazon Ember.ttf", 16)
font_body_bold  = load_font("Amazon Ember Bold.ttf", 16)
font_small      = load_font("Amazon Ember.ttf", 14)
font_tiny       = load_font("Amazon Ember Bold.ttf", 13)
font_wi_large   = load_font("weathericons-regular-webfont.ttf", 38)
font_wi_small   = load_font("weathericons-regular-webfont.ttf", 24)

# --- 5. RENDER CANVAS ---
img = Image.new('RGB', (WIDTH, HEIGHT), C_WHITE)
draw = ImageDraw.Draw(img)

today_events, tomorrow_events, later_events = get_calendar_events()
ecowitt = get_ecowitt_data()
bom = get_balingup_bom()

tz_wa = datetime.timezone(datetime.timedelta(hours=8))
now_wa = datetime.datetime.now(tz_wa)

# --- HEADER BAR ---
draw.rounded_rectangle([(12, 10), (WIDTH - 12, 48)], radius=14, fill=C_WHITE, outline=C_BLACK, width=2)
date_title_str = now_wa.strftime("%A, %d %B %Y")
time_now_str = now_wa.strftime("%I:%M %p").lstrip('0')

draw_sharp_text(img, (26, 17), date_title_str, font_title, C_BLACK)
draw_sharp_text(img, (WIDTH - 150, 21), f"Updated {time_now_str}", font_small, C_BLACK)

# --- EASTER EGGS ---
if now_wa.month == 10 and now_wa.day == 31:
    draw_sharp_text(img, (380, 18), "🎃", font_title, C_ORANGE)
elif now_wa.month == 12 and now_wa.day >= 24:
    draw_sharp_text(img, (380, 18), "🎄", font_title, C_GREEN)

# --- LEFT COLUMN: AGENDA (Width 382px) ---
draw.rounded_rectangle([(12, 58), (394, 335)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)

# Section: Today
draw.rounded_rectangle([(24, 68), (110, 92)], radius=8, fill=C_BLACK)
draw_sharp_text(img, (38, 71), "Today", font_card_head, C_WHITE)

y_cursor = 102
if today_events:
    for _, t_str, summ, e_color in today_events[:4]:
        draw.ellipse([26, y_cursor + 4, 34, y_cursor + 12], fill=e_color)
        label = summ if not t_str else f"{t_str} - {summ}"
        draw_sharp_text(img, (42, y_cursor), label[:32] + "..." if len(label) > 34 else label, font_body, C_BLACK)
        y_cursor += 24
else:
    draw_sharp_text(img, (28, y_cursor), "No events scheduled today", font_body, C_BLACK)
    y_cursor += 24

# Section: Tomorrow
y_cursor = max(y_cursor + 10, 192)
draw.rounded_rectangle([(24, y_cursor), (140, y_cursor + 24)], radius=8, fill=C_BLACK)
draw_sharp_text(img, (38, y_cursor + 3), "Tomorrow", font_card_head, C_WHITE)
y_cursor += 34

if tomorrow_events:
    for _, t_str, summ, e_color in tomorrow_events[:4]:
        draw.ellipse([26, y_cursor + 4, 34, y_cursor + 12], fill=e_color)
        label = summ if not t_str else f"{t_str} - {summ}"
        draw_sharp_text(img, (42, y_cursor), label[:32] + "..." if len(label) > 34 else label, font_body, C_BLACK)
        y_cursor += 24
else:
    draw_sharp_text(img, (28, y_cursor), "No events scheduled tomorrow", font_body, C_BLACK)

# Card 2: Looking Ahead
draw.rounded_rectangle([(12, 345), (394, 468)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)
draw.rounded_rectangle([(24, 355), (170, 379)], radius=8, fill=C_BLACK)
draw_sharp_text(img, (36, 358), "Looking Ahead", font_card_head, C_WHITE)

y_ahead = 390
if later_events:
    for d, t_str, summ, e_color in later_events[:3]:
        day_tag = d.strftime("%a %d")
        draw.ellipse([26, y_ahead + 4, 34, y_ahead + 12], fill=e_color)
        draw_sharp_text(img, (42, y_ahead), day_tag, font_body_bold, C_BLACK)
        draw_sharp_text(img, (110, y_ahead), summ[:24] + "..." if len(summ) > 26 else summ, font_body, C_BLACK)
        y_ahead += 24
else:
    draw_sharp_text(img, (28, y_ahead), "No upcoming events this week.", font_body, C_BLACK)


# --- RIGHT COLUMN: WEATHER WIDGETS ---
# Card 3: Weather Station
draw.rounded_rectangle([(406, 58), (WIDTH - 12, 235)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)
draw.rounded_rectangle([(419, 68), (565, 92)], radius=8, fill=C_BLACK)
draw_sharp_text(img, (431, 71), "Weather Station", font_card_head, C_WHITE)

if ecowitt:
    draw_sharp_text(img, (421, 96), f"{ecowitt['temp_c']}°", font_hero, C_BLACK)
    draw_sharp_text(img, (564, 112), f"Humidity: {ecowitt['humidity']}%", font_body, C_BLACK)

    if bom and "yesterday_high" in bom and "overnight_low" in bom:
        stat_line = f"Yesterday High: {bom['yesterday_high']}°C  |  Low: {bom['overnight_low']}°C"
        draw_sharp_text(img, (421, 146), stat_line, font_small, C_BLACK)

    draw.line([(421, 166), (776, 166)], fill=C_BLACK, width=2)

    draw_sharp_text(img, (421, 174), f"Rain 24h: {ecowitt['rain_24h']} mm", font_body, C_BLACK)
    draw_sharp_text(img, (574, 174), f"Weekly: {ecowitt['rain_weekly']} mm", font_body, C_BLACK)
else:
    draw_sharp_text(img, (421, 110), "Sensors connecting...", font_body, C_BLACK)

# Card 4: Balingup Forecast & Solar Times
draw.rounded_rectangle([(406, 245), (WIDTH - 12, 468)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)
draw.rounded_rectangle([(419, 255), (665, 279)], radius=8, fill=C_BLACK)
draw_sharp_text(img, (431, 258), "Balingup Weather Forecast", font_card_head, C_WHITE)

if bom:
    # Today Icon & Forecast
    t_icon, t_color = get_weather_icon(bom["today"]["code"])
    draw_sharp_text(img, (419, 280), t_icon, font_wi_large, t_color)
    draw_sharp_text(img, (473, 286), f"Today  Max {bom['today']['max']}° | Min {bom['today']['min']}°", font_body, C_BLACK)
    draw_sharp_text(img, (473, 306), f"Precip: {bom['today']['rain_prob']}%", font_small, C_BLACK)

    # Tomorrow Icon & Forecast
    tm_icon, tm_color = get_weather_icon(bom["tomorrow"]["code"])
    draw_sharp_text(img, (419, 326), tm_icon, font_wi_large, tm_color)
    draw_sharp_text(img, (473, 332), f"Tomorrow  Max {bom['tomorrow']['max']}° | Min {bom['tomorrow']['min']}°", font_body, C_BLACK)
    draw_sharp_text(img, (473, 352), f"Precip: {bom['tomorrow']['rain_prob']}%", font_small, C_BLACK)

    # Solar Strip Banner
    draw.rounded_rectangle([(417, 376), (776, 404)], radius=8, fill=C_WHITE, outline=C_BLACK, width=2)
    moon_name = get_moon_phase_name(now_wa.date())
    
    # Draw moon name in orange for visual pop
    draw_sharp_text(img, (425, 383), f"Moon:", font_tiny, C_BLACK)
    draw_sharp_text(img, (465, 383), f"{moon_name}", font_tiny, C_ORANGE)
    solar_summary = f"•  Dawn {bom['first_light']}  •  Rise {bom['sunrise']}  •  Set {bom['sunset']}"
    draw_sharp_text(img, (560, 383), solar_summary, font_tiny, C_BLACK)

    # Mini 5-Day Strip
    col_width = (776 - 417) // 5
    for i, item in enumerate(bom.get("next_5_days", [])):
        center_x = 417 + (i * col_width) + 35
        n_icon, n_color = get_weather_icon(item["code"])
        draw_sharp_text(img, (center_x - 12, 404), n_icon, font_wi_small, n_color)
        draw_sharp_text(img, (center_x - 12, 438), item["day_name"], font_tiny, C_BLACK)
else:
    draw_sharp_text(img, (419, 310), "Forecast unavailable", font_body, C_BLACK)

# --- SAVE IMAGE ---
img.save("dashboard.png", "PNG", optimize=True)
log("Saved perfectly masked 7-color dashboard successfully!")
