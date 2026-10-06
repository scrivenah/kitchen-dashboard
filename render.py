# --- 1. GOOGLE CALENDAR FETCHER & PARSER ---
def get_calendar_events():
    ics_urls = os.environ.get("CALENDAR_ICS_URLS", "")
    if not ics_urls:
        print("LOG: No CALENDAR_ICS_URLS secret configured.")
        return []

    tz_wa = datetime.timezone(datetime.timedelta(hours=8))
    now_wa = datetime.datetime.now(tz_wa)
    today = now_wa.date()
    tomorrow = today + datetime.timedelta(days=1)

    print(f"LOG: System date is {today} (Tomorrow is {tomorrow})")

    url_list = [u.strip() for u in ics_urls.split(",") if u.strip()]
    print(f"LOG: Total calendar feeds configured: {len(url_list)}")

    events = []

    for idx, url in enumerate(url_list):
        # Mask secret part of URL in logs
        safe_url = url.split("?")[0][:45] + "..."
        try:
            res = requests.get(url, timeout=12)
            print(f"LOG [Feed #{idx+1}]: HTTP {res.status_code} from {safe_url}")
            if res.status_code != 200:
                continue

            cal = Calendar.from_ical(res.text)
            parsed_count = 0
            for component in cal.walk():
                if component.name == "VEVENT":
                    parsed_count += 1
                    summary = str(component.get("summary", "Untitled"))
                    dtstart_prop = component.get("dtstart")
                    if not dtstart_prop:
                        continue
                    dtstart = dtstart_prop.dt
                    dtend_prop = component.get("dtend")
                    dtend = dtend_prop.dt if dtend_prop else dtstart

                    # Convert start to date
                    if isinstance(dtstart, datetime.datetime):
                        dtstart_local = dtstart.astimezone(tz_wa)
                        start_date = dtstart_local.date()
                        time_str = dtstart_local.strftime("%I:%M %p").lstrip('0')
                    else:
                        start_date = dtstart
                        time_str = "All Day"

                    # Convert end to date
                    if isinstance(dtend, datetime.datetime):
                        end_date = dtend.astimezone(tz_wa).date()
                    else:
                        end_date = dtend

                    # For all-day events, Google's end date is exclusive
                    if time_str == "All Day" and end_date > start_date:
                        effective_end = end_date - datetime.timedelta(days=1)
                    else:
                        effective_end = end_date

                    # Print out events close to this month for inspection
                    if abs((start_date - today).days) < 15:
                        print(f"  -> Found event: '{summary}' | Range: {start_date} to {effective_end} | Time: {time_str}")

                    # Matching today
                    if start_date <= today <= effective_end:
                        print(f"     *** MATCHED TODAY: {summary}")
                        events.append((today, time_str, summary, "TODAY"))

                    # Matching tomorrow
                    if start_date <= tomorrow <= effective_end:
                        print(f"     *** MATCHED TOMORROW: {summary}")
                        events.append((tomorrow, time_str, summary, "TOMORROW"))

            print(f"LOG [Feed #{idx+1}]: Checked {parsed_count} total events.")
        except Exception as e:
            print(f"LOG [Feed #{idx+1}] Error: {e}")

    # Deduplicate
    seen = set()
    deduped = []
    for ev in events:
        key = (ev[0], ev[1], ev[2], ev[3])
        if key not in seen:
            seen.add(key)
            deduped.append(ev)

    deduped.sort(key=lambda x: (x[0], 0 if x[1] == "All Day" else 1, x[1]))
    return deduped
