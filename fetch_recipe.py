import os
import sys
import json
import time
import re

try:
    from curl_cffi import requests as c_requests
except ImportError:
    import requests as c_requests

from recipe_scrapers import scrape_me
from google import genai

def condense_with_gemini(recipe_url, raw_title, raw_yields, raw_time, raw_ingredients, raw_instructions):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable is missing or empty!")
        return None

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are an expert chef's assistant formatting a recipe for an 800x480 e-paper kitchen display.
Your job is to condense the recipe so it fits on a SINGLE screen with zero fluff.

Recipe: {raw_title}
Source URL / Site: {recipe_url}
Yield: {raw_yields}
Time: {raw_time}

Raw Ingredients:
{chr(10).join(raw_ingredients)}

Raw Steps:
{chr(10).join(raw_instructions)}

Requirements:
1. "title": Include the author or publication attribution in possessive form, followed by the specific recipe name (e.g. "RecipeTin's BBQ Pork Ribs", "Jamie Oliver's Kedgeree", "BBC Good Food's Drunken Noodles", "Tasty's Stout Chocolate Cake"). Keep it under 42 characters.
2. "meta": Concise summary like "Serves 4 • 45 mins" or "Yield: 12 • 180°C • 35m".
3. "ingredients": Exactly 8 to 12 essential items. Max 38 characters per line.
   - ALWAYS PRESERVE QUANTITIES: Keep exact measurements for aromatics, liquids, and spices.
   - METRIC CONVERSIONS: Convert weights to grams (g/kg), volumes to ml/litres, and oven temps to °C.
   - COMPONENT LABELS: If a recipe has separate parts (e.g. sauce vs meat), prefix concisely: "Pork: 500g mince", "Sauce: 60ml soy".
   - SPICE & GARNISH BUNDLING: If bundling minor items into one line, keep measurements (e.g. "1 onion, 2 cloves garlic, 3cm ginger" or "2 tbsp curry powder, 1 tsp mustard seeds").
   - OMIT TRIVIAL BASICS: Omit minor unmeasured water/salt/pepper if the list exceeds 12 items.
4. "steps": Exactly 5 to 6 concise action steps WITHOUT leading step numbers.
   - HARDWARE CONVERSIONS: Convert cake pans, skillets, and dish sizes from inches to cm (e.g. 8-inch -> 20cm tin, 9x13-inch -> 23x33cm dish).
   - LENGTH & FLOW: Write complete, natural imperative sentences of 14 to 22 words (max 120 characters).
   - CRITICAL PRECISION: Retain vital pan temperatures, heat settings (low/med/high), and cooking/baking times.

Output strictly valid JSON matching this schema:
{{
  "title": "...",
  "meta": "...",
  "ingredients": ["...", "..."],
  "steps": ["...", "..."]
}}
"""

    candidate_models = [
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
    ]

    for model_name in candidate_models:
        for attempt in range(2):
            try:
                print(f"Attempting condensation with model: {model_name} (try {attempt + 1})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                
                # Strip any accidental leading digits like "1. " or "2) "
                if "steps" in data:
                    data["steps"] = [re.sub(r'^\d+[\.\)]\s*', '', s) for s in data["steps"]]

                print(f"SUCCESS: Gemini ({model_name}) condensed the recipe successfully!")
                return data
            except Exception as e:
                err_msg = str(e)
                print(f"Warning: {model_name} failed with: {err_msg}")
                if "503" in err_msg or "UNAVAILABLE" in err_msg:
                    time.sleep(2)
                    continue
                break

    print("All AI attempts exhausted; falling back to raw scraper data.")
    return None

def parse_and_save(recipe_url):
    print(f"Fetching recipe from: {recipe_url}")
    
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }

    try:
        # impersonate="chrome120" bypasses Akamai & Cloudflare TLS fingerprinting
        response = c_requests.get(recipe_url, headers=headers, impersonate="chrome120", timeout=15)
    except TypeError:
        # Fallback if standard requests is used
        response = c_requests.get(recipe_url, headers=headers, timeout=15)
        
    response.raise_for_status()

    try:
    scraper = scrape_me(recipe_url, html_str=response.text)
except TypeError:
    scraper = scrape_me(recipe_url)

    raw_title = scraper.title()
    try:
        raw_yields = scraper.yields()
    except Exception:
        raw_yields = "N/A"

    try:
        raw_time = f"{scraper.total_time()} mins"
    except Exception:
        raw_time = "N/A"

    raw_ingredients = scraper.ingredients()
    try:
        raw_instructions = scraper.instructions_list()
    except Exception:
        raw_instructions = [scraper.instructions()]

    condensed = condense_with_gemini(
        recipe_url, raw_title, raw_yields, raw_time, raw_ingredients, raw_instructions
    )

    if not condensed:
        condensed = {
            "title": raw_title[:40],
            "meta": f"{raw_yields} • {raw_time}",
            "ingredients": raw_ingredients[:12],
            "steps": raw_instructions[:6]
        }

    with open("current_recipe.json", "w") as f:
        json.dump(condensed, f, indent=2)

    print("Saved recipe payload to current_recipe.json successfully.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = os.environ.get("RECIPE_URL")

    if not url:
        print("ERROR: No URL provided via argument or RECIPE_URL environment variable.")
        sys.exit(1)

    parse_and_save(url)
