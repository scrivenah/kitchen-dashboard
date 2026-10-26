import os
import requests
import datetime
from dateutil import rrule as drrule
from icalendar import Calendar
from playwright.sync_api import sync_playwright

WIDTH, HEIGHT = 800, 480

def log(msg):
    print(f"LOG: {msg}", flush=True)

# 1. Fetch Calendar
def get_calendar_events():
    ics_urls = os.environ.get("CALENDAR_ICS_URLS", "")
    if not ics_urls:
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
        color_class = "text-red-700" if is_airbnb else ("text-amber-700" if "41p9gaols1it9m" in url.lower() else "text-blue-700")

        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
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

                    curr = base_start
                    while curr <= effective_end:
                        if today <= curr <= future_cutoff:
                            raw_events.append((curr, time_str, summary, color_class))
                        curr += datetime.timedelta(days=1)
        except Exception as e:
            log(f"Feed error: {e}")

    unique = list({(e[0], e[1], e[2]): e for e in raw_events}.values())
    unique.sort(key=lambda x: (x[0], 0 if x[1] == "" else 1, x[1]))

    return [e for e in unique if e[0] == today], [e for e in unique if e[0] == tomorrow], [e for e in unique if e[0] > tomorrow]

# 2. Fetch Ecowitt
def get_ecowitt_data():
    app_key = os.environ.get("ECOWITT_APPLICATION_KEY")
    api_key = os.environ.get("ECOWITT_API_KEY")
    mac = os.environ.get("ECOWITT_MAC")
    if not all([app_key, api_key, mac]):
        return {"temp_c": "--", "humidity": "--", "rain_24h": 0.0, "rain_weekly": 0.0}

    try:
        url = f"https://api.ecowitt.net/api/v3/device/real_time?application_key={app_key}&api_key={api_key}&mac={mac}&call_back=outdoor,rainfall"
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
    except Exception:
        return {"temp_c": "--", "humidity": "--", "rain_24h": 0.0, "rain_weekly": 0.0}

# 3. Fetch BOM Forecast
def get_bom():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=-33.7865&longitude=115.9838&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,sunrise,sunset&hourly=temperature_2m&past_days=1&forecast_days=7&timezone=Australia%2FPerth"
        res = requests.get(url, timeout=10).json()
        daily = res["daily"]
        dates = [datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in daily["time"]]

        def fmt_time(iso, delta=0):
            return (datetime.datetime.fromisoformat(iso) + datetime.timedelta(minutes=delta)).strftime("%I:%M %p").lstrip('0')

        return {
            "yesterday_high": round(daily["temperature_2m_max"][0]),
            "overnight_low": round(daily["temperature_2m_min"][1]),
            "first_light": fmt_time(daily["sunrise"][1], -26),
            "sunrise": fmt_time(daily["sunrise"][1]),
            "sunset": fmt_time(daily["sunset"][1]),
            "last_light": fmt_time(daily["sunset"][1], 26),
            "today_max": round(daily["temperature_2m_max"][1]),
            "today_min": round(daily["temperature_2m_min"][1]),
            "today_rain_sum": daily.get("precipitation_sum", [0])[1] or 0.0,
            "today_rain_prob": daily.get("precipitation_probability_max", [0])[1] or 0,
            "tmrw_max": round(daily["temperature_2m_max"][2]),
            "tmrw_min": round(daily["temperature_2m_min"][2]),
            "tmrw_rain_sum": daily.get("precipitation_sum", [0, 0, 0])[2] or 0.0,
            "tmrw_rain_prob": daily.get("precipitation_probability_max", [0, 0, 0])[2] or 0,
            "next_5": [{"day": dates[i].strftime("%a"), "max": round(daily["temperature_2m_max"][i]), "min": round(daily["temperature_2m_min"][i])} for i in range(3, min(8, len(dates)))]
        }
    except Exception:
        return None

today_ev, tomorrow_ev, ahead_ev = get_calendar_events()
eco = get_ecowitt_data()
bom = get_bom() or {}

# Format HTML Snippets
def format_events(ev_list, empty_msg):
    if not ev_list:
        return f'<div class="text-xs text-neutral-400 italic">{empty_msg}</div>'
    out = []
    for d, t, s, c in ev_list[:3]:
        time_tag = f'<span class="font-mono text-[11px] text-neutral-500 mr-1.5">{t}</span>' if t else ''
        out.append(f'<div class="text-xs truncate font-medium flex items-center"><span class="w-1.5 h-1.5 rounded-full bg-current {c} mr-2 flex-shrink-0"></span>{time_tag}<span class="truncate">{s}</span></div>')
    return "\n".join(out)

today_html = format_events(today_ev, "No events scheduled")
tmrw_html = format_events(tomorrow_ev, "No events scheduled")

ahead_html = []
for d, t, s, c in ahead_ev[:3]:
    day_lbl = d.strftime("%a %d")
    ahead_html.append(f'<div class="text-xs truncate text-neutral-700 flex items-center"><span class="font-semibold text-neutral-900 w-12 flex-shrink-0">{day_lbl}</span><span class="truncate">{s}</span></div>')
ahead_out = "\n".join(ahead_html) if ahead_html else '<div class="text-xs text-neutral-400 italic">No upcoming events</div>'

five_day_html = "".join([f'<div class="flex-1"><div class="text-xs font-bold uppercase">{d["day"]}</div><div class="text-xs font-medium text-neutral-600">{d["max"]}° / {d["min"]}°</div></div>' for d in bom.get("next_5", [])])

tz_wa = datetime.timezone(datetime.timedelta(hours=8))
now_wa = datetime.datetime.now(tz_wa)

with open("dashboard_template.html", "r", encoding="utf-8") as f:
    template = f.read()

replacements = {
    "{{DATE_STRING}}": now_wa.strftime("%A, %d %B %Y"),
    "{{UPDATE_TIME}}": now_wa.strftime("%I:%M %p").lstrip('0'),
    "{{TODAY_EVENTS}}": today_html,
    "{{TOMORROW_EVENTS}}": tmrw_html,
    "{{AHEAD_EVENTS}}": ahead_out,
    "{{TEMP_C}}": str(eco.get("temp_c", "--")),
    "{{HUMIDITY}}": str(eco.get("humidity", "--")),
    "{{YESTERDAY_HIGH}}": str(bom.get("yesterday_high", "--")),
    "{{OVERNIGHT_LOW}}": str(bom.get("overnight_low", "--")),
    "{{RAIN_24H}}": str(eco.get("rain_24h", 0.0)),
    "{{RAIN_WEEKLY}}": str(eco.get("rain_weekly", 0.0)),
    "{{TODAY_MAX}}": str(bom.get("today_max", "--")),
    "{{TODAY_MIN}}": str(bom.get("today_min", "--")),
    "{{TODAY_RAIN_PROB}}": str(bom.get("today_rain_prob", 0)),
    "{{TODAY_RAIN_SUM}}": str(bom.get("today_rain_sum", 0.0)),
    "{{TMRW_MAX}}": str(bom.get("tmrw_max", "--")),
    "{{TMRW_MIN}}": str(bom.get("tmrw_min", "--")),
    "{{TMRW_RAIN_PROB}}": str(bom.get("tmrw_rain_prob", 0)),
    "{{TMRW_RAIN_SUM}}": str(bom.get("tmrw_rain_sum", 0.0)),
    "{{FIRST_LIGHT}}": bom.get("first_light", "--"),
    "{{SUNRISE}}": bom.get("sunrise", "--"),
    "{{SUNSET}}": bom.get("sunset", "--"),
    "{{LAST_LIGHT}}": bom.get("last_light", "--"),
    "{{FIVE_DAY_FORECAST}}": five_day_html,
}

for k, v in replacements.items():
    template = template.replace(k, str(v))

with open("rendered_page.html", "w", encoding="utf-8") as f:
    f.write(template)

# Playwright Snapshot
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1.0)
    page.goto(f"file://{os.path.abspath('rendered_page.html')}")
    page.screenshot(path="dashboard.png")
    browser.close()

log("Pristine web dashboard rendered to dashboard.png")
