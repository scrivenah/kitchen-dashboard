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

# --- 1. CALENDAR FETCHER ---
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
        
        if is_airbnb: event_color = C_RED
        elif is_holiday: event_color = C_ORANGE
        else: event_color = C_BLUE

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
            pass

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
            "rain_event": round(float(rainfall.get("event", {}).get("value", 0.0)), 1)
        }
    except: return None

# --- 3. OPEN-METEO WEATHER FETCHER ---
def get_balingup_bom():
    url = "https://api.open-meteo.com/v1/forecast?latitude=-33.7865&longitude=115.9838&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,sunrise,sunset&hourly=temperature_2m&past_days=1&forecast_days=7&timezone=Australia%2FPerth"
    try:
        res = requests.get(url, timeout=10).json()
        daily = res["daily"]
        dates = [datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in daily["time"]]
        
        def fmt_time(iso):
            if not iso: return "--:--"
            return datetime.datetime.fromisoformat(iso).strftime("%I:%M %p").lstrip('0')

        return {
            "yesterday_high": round(daily["temperature_2m_max"][0]),
            "overnight_low": round(daily["temperature_2m_min"][1]),
            "today_date": dates[1],
            "sunrise": fmt_time(daily["sunrise"][1]),
            "sunset": fmt_time(daily["sunset"][1]),
            "today": {
                "code": daily["weathercode"][1],
                "max": round(daily["temperature_2m_max"][1]),
                "min": round(daily["temperature_2m_min"][1]),
                "rain_prob": daily.get("precipitation_probability_max", [0]*8)[1] or 0,
                "rain_sum": daily.get("precipitation_sum", [0]*8)[1] or 0.0,
            },
            "tomorrow": {
                "code": daily["weathercode"][2],
                "max": round(daily["temperature_2m_max"][2]),
                "min": round(daily["temperature_2m_min"][2]),
                "rain_prob": daily.get("precipitation_probability_max", [0]*8)[2] or 0,
                "rain_sum": daily.get("precipitation_sum", [0]*8)[2] or 0.0,
            },
            # Restored to full 5 Days
            "next_5_days": [{
                "day_name": dates[i].strftime("%a").capitalize(), 
                "code": daily["weathercode"][i],
                "max": round(daily["temperature_2m_max"][i]),
                "min": round(daily["temperature_2m_min"][i]),
                "rain": daily.get("precipitation_sum", [0]*8)[i] or 0.0
            } for i in range(3, min(8, len(dates)))]
        }
    except: return None

# --- 4. ASSET LOADERS ---
def get_weather_icon(wmo_code):
    if wmo_code in [0, 1]: return ("\uf00d", C_YELLOW)
    elif wmo_code in [2, 3]: return ("\uf013", C_BLACK)
    elif wmo_code in [45, 48]: return ("\uf014", C_BLACK)
    elif wmo_code in [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82]: return ("\uf019", C_BLUE)
    elif wmo_code in [71, 73, 75, 77, 85, 86]: return ("\uf01b", C_BLUE)
    elif wmo_code in [95, 96, 99]: return ("\uf01e", C_RED)
    return ("\uf00d", C_YELLOW)

def get_moon_phase(date_obj):
    new_moon = datetime.date(2000, 1, 6)
    lunar_days = (date_obj - new_moon).days % 29.53058867
    icon_index = int(round((lunar_days / 29.53058867) * 28)) % 28
    sh_visual_index = (28 - icon_index) % 28
    
    if sh_visual_index == 0: moon_icon = '\uf0eb'
    else: moon_icon = chr(0xf0cf + sh_visual_index)
    
    if icon_index == 0: name = 'New Moon'
    elif 1 <= icon_index <= 6: name = 'Waxing Crescent'
    elif icon_index == 7: name = 'First Quarter'
    elif 8 <= icon_index <= 13: name = 'Waxing Gibbous'
    elif icon_index == 14: name = 'Full Moon'
    elif 15 <= icon_index <= 20: name = 'Waning Gibbous'
    elif icon_index == 21: name = 'Last Quarter'
    else: name = 'Waning Crescent'
    
    return (name, moon_icon)

def load_font(filename, size):
    try: return ImageFont.truetype(f"font/{filename}", size)
    except: return ImageFont.load_default()

# ENFORCING MINIMUM SIZE 18 FOR READABILITY
font_hero       = load_font("Amazon Ember Bold.ttf", 46)
font_title      = load_font("Amazon Ember Bold.ttf", 20)
font_body       = load_font("Amazon Ember.ttf", 18)
font_body_bold  = load_font("Amazon Ember Bold.ttf", 18)
font_wi_large   = load_font("weathericons-regular-webfont.ttf", 42)
font_wi_small   = load_font("weathericons-regular-webfont.ttf", 34)
font_wi_body    = load_font("weathericons-regular-webfont.ttf", 20)

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
draw.text((26, 15), now_wa.strftime("%A, %d %B %Y"), font=font_title, fill=C_BLACK)
draw.text((WIDTH - 200, 16), f"Updated {now_wa.strftime('%I:%M %p').lstrip('0')}", font=font_body, fill=C_BLACK)

if now_wa.month == 10 and now_wa.day == 31: draw.text((380, 16), "🎃", font=font_title, fill=C_ORANGE)
elif now_wa.month == 12 and now_wa.day >= 24: draw.text((380, 16), "🎄", font=font_title, fill=C_GREEN)

# --- LEFT COLUMN: AGENDA (Narrowed to 330px wide to give weather more room) ---
draw.rounded_rectangle([(12, 58), (342, 335)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)
draw.text((26, 68), "Today", font=font_title, fill=C_BLACK)

y_cursor = 100
if today_events:
    for _, t_str, summ, e_color in today_events[:3]:
        draw.ellipse([26, y_cursor + 5, 34, y_cursor + 13], fill=e_color)
        label = summ if not t_str else f"{t_str} - {summ}"
        draw.text((42, y_cursor), label[:23] + "..." if len(label) > 25 else label, font=font_body, fill=C_BLACK)
        y_cursor += 28
else:
    draw.text((28, y_cursor), "No events scheduled today", font=font_body, fill=C_BLACK)
    y_cursor += 28

y_cursor = max(y_cursor + 12, 192)
draw.text((26, y_cursor), "Tomorrow", font=font_title, fill=C_BLACK)
y_cursor += 32
if tomorrow_events:
    for _, t_str, summ, e_color in tomorrow_events[:3]:
        draw.ellipse([26, y_cursor + 5, 34, y_cursor + 13], fill=e_color)
        label = summ if not t_str else f"{t_str} - {summ}"
        draw.text((42, y_cursor), label[:23] + "..." if len(label) > 25 else label, font=font_body, fill=C_BLACK)
        y_cursor += 28
else:
    draw.text((28, y_cursor), "No events scheduled tomorrow", font=font_body, fill=C_BLACK)

draw.rounded_rectangle([(12, 345), (342, 468)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)
draw.text((26, 355), "Looking Ahead", font=font_title, fill=C_BLACK)
y_ahead = 392
if later_events:
    for d, t_str, summ, e_color in later_events[:2]:
        draw.ellipse([26, y_ahead + 5, 34, y_ahead + 13], fill=e_color)
        draw.text((42, y_ahead), d.strftime("%a %d"), font=font_body_bold, fill=C_BLACK)
        draw.text((114, y_ahead), summ[:18] + "..." if len(summ) > 20 else summ, font=font_body, fill=C_BLACK)
        y_ahead += 28
else:
    draw.text((28, y_ahead), "No upcoming events this week.", font=font_body, fill=C_BLACK)


# --- RIGHT COLUMN: WEATHER (Expanded to 446px wide) ---
draw.rounded_rectangle([(354, 58), (WIDTH - 12, 468)], radius=16, fill=C_WHITE, outline=C_BLACK, width=2)

draw.text((368, 68), "Weather Station", font=font_title, fill=C_BLACK)

if ecowitt:
    draw.text((368, 96), f"{ecowitt['temp_c']}°", font=font_hero, fill=C_BLACK)
    # Using humidity drop symbol instead of text
    draw.text((504, 114), "\uf07a", font=font_wi_body, fill=C_BLACK)
    draw.text((528, 114), f"{ecowitt['humidity']}%", font=font_body, fill=C_BLACK)
    
    draw.text((368, 150), f"Yesterday: {bom['yesterday_high']}° | {bom['overnight_low']}°" if bom else "", font=font_body, fill=C_BLACK)
    draw.text((368, 176), f"Rain 24h: {ecowitt['rain_24h']}mm   |   Event: {ecowitt['rain_event']}mm", font=font_body, fill=C_BLACK)
else:
    draw.text((368, 114), "Sensors connecting...", font=font_body, fill=C_BLACK)

draw.line([(368, 206), (774, 206)], fill=C_BLACK, width=2)
draw.text((368, 216), "Balingup Weather Forecast", font=font_title, fill=C_BLACK)

if bom:
    # Counter-act top padding in weathericons font by pushing icon Y up
    t_icon, t_color = get_weather_icon(bom["today"]["code"])
    draw.text((368, 234), t_icon, font=font_wi_large, fill=t_color) 
    draw.text((430, 244), f"Today  Max {bom['today']['max']}° | Min {bom['today']['min']}°", font=font_body_bold, fill=C_BLACK)
    
    # Umbrella and droplet symbols for rain
    draw.text((430, 268), "\uf084", font=font_wi_body, fill=C_BLACK) 
    draw.text((454, 268), f"{bom['today']['rain_prob']}%", font=font_body, fill=C_BLACK)
    draw.text((510, 268), "\uf078", font=font_wi_body, fill=C_BLUE) 
    draw.text((530, 268), f"{bom['today']['rain_sum']}mm", font=font_body, fill=C_BLACK)

    tm_icon, tm_color = get_weather_icon(bom["tomorrow"]["code"])
    draw.text((368, 288), tm_icon, font=font_wi_large, fill=tm_color)
    draw.text((430, 298), f"Tomorrow  Max {bom['tomorrow']['max']}° | Min {bom['tomorrow']['min']}°", font=font_body_bold, fill=C_BLACK)
    
    draw.text((430, 322), "\uf084", font=font_wi_body, fill=C_BLACK)
    draw.text((454, 322), f"{bom['tomorrow']['rain_prob']}%", font=font_body, fill=C_BLACK)
    draw.text((510, 322), "\uf078", font=font_wi_body, fill=C_BLUE) 
    draw.text((530, 322), f"{bom['tomorrow']['rain_sum']}mm", font=font_body, fill=C_BLACK)

    # Sunrise and Sunset with symbols
    draw.text((368, 354), "\uf051", font=font_wi_body, fill=C_BLACK)
    draw.text((394, 354), bom['sunrise'], font=font_body, fill=C_BLACK)
    draw.text((478, 354), "\uf052", font=font_wi_body, fill=C_BLACK)
    draw.text((504, 354), bom['sunset'], font=font_body, fill=C_BLACK)
    
    moon_name, moon_icon = get_moon_phase(now_wa.date())
    draw.text((614, 342), moon_icon, font=font_wi_small, fill=C_BLACK)
    draw.text((656, 354), moon_name, font=font_body, fill=C_BLACK)

    # 5-Day Strip (Mathematically centered using Pillow anchor="mt")
    col_width = (WIDTH - 12 - 354) / 5
    for i, item in enumerate(bom.get("next_5_days", [])):
        cx = 354 + (i * col_width) + (col_width / 2)
        n_icon, n_color = get_weather_icon(item["code"])
        
        draw.text((cx, 386), item["day_name"], font=font_body_bold, fill=C_BLACK, anchor="mt")
        draw.text((cx, 396), n_icon, font=font_wi_small, fill=n_color, anchor="mt")
        draw.text((cx, 434), f"{item['max']}°|{item['min']}°", font=font_body, fill=C_BLACK, anchor="mt")
        draw.text((cx, 456), f"{item['rain']}mm", font=font_body, fill=C_BLACK, anchor="mt")

img.save("dashboard.png", "PNG", optimize=True)
log("Optimized readability layout generated successfully!")
