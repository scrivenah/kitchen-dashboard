import os
import json
import re
import time
import requests
from recipe_scrapers import scrape_html
from google import genai

def convert_units_to_metric(text):
    # Fahrenheit to Celsius
    def f_to_c(m):
        f = float(m.group(1))
        c = round(((f - 32) * 5 / 9) / 5) * 5
        return f"{c}°C"
    text = re.sub(r'(\d+(?:\.\d+)?)\s*(?:°\s*|degrees?\s*)?[Ff](?:ahrenheit)?\b', f_to_c, text)

    # Pounds to grams / kg
    def lbs_to_metric(m):
        val = float(m.group(1))
        grams = val * 453.592
        return f"{round(grams / 1000, 1)} kg" if grams >= 1000 else f"{round(grams)} g"
    text = re.sub(r'(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)\b', lbs_to_metric, text, flags=re.IGNORECASE)

    # Ounces to grams
    def oz_to_g(m):
        val = float(m.group(1))
        return f"{round(val * 28.35)} g"
    text = re.sub(r'(\d+(?:\.\d+)?)\s*(?:oz|ounces?)\b', oz_to_g, text, flags=re.IGNORECASE)

    # Sticks of butter
    def sticks_to_g(m):
        val = float(m.group(1))
        return f"{round(val * 113)} g butter"
    text = re.sub(r'(\d+(?:\.\d+)?)\s*sticks?\s+of\s+butter\b', sticks_to_g, text, flags=re.IGNORECASE)

    return text

def condense_with_gemini(raw_title, raw_yields, raw_time, raw_ingredients, raw_instructions):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable is missing or empty!")
        return None

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are an expert chef's assistant formatting a recipe for an 800x480 e-paper kitchen display.
Your job is to condense the recipe so it fits on a SINGLE screen with zero fluff.

Recipe: {raw_title}
Yield: {raw_yields}
Time: {raw_time}

Raw Ingredients:
{chr(10).join(raw_ingredients)}

Raw Steps:
{chr(10).join(raw_instructions)}

Requirements:
1. "title": Shortened title under 30 characters.
2. "meta": Concise summary like "Serves 6 • 150 mins".
3. "ingredients": List of essential ingredients with metric units (grams, ml, °C). Max 12 items.
   - CRITICAL: Keep each ingredient line under 30 characters so text does not truncate.
   - For complex rubs/spices, summarize simply (e.g. "15g BBQ spice rub" instead of listing each spice).
4. "steps": Exactly 5 to 6 concise action steps WITHOUT leading step numbers.
   - Write clear, grammatically natural instructions.
   - Keep critical temperatures (°C), pan sizes, and baking times.

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

    print("All AI attempts exhausted; falling back to basic raw scraper.")
    return None

def parse_and_save(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    scraper = scrape_html(response.text, org_url=url)

    raw_title = scraper.title()
    raw_yields = scraper.yields()
    raw_time = scraper.total_time()
    raw_ingredients = scraper.ingredients()
    raw_instructions = scraper.instructions_list()

    condensed = condense_with_gemini(raw_title, raw_yields, raw_time, raw_ingredients, raw_instructions)

    if not condensed:
        print("Falling back to basic raw scraper fallback...")
        clean_ingredients = [convert_units_to_metric(i.strip()) for i in raw_ingredients if i.strip()]
        condensed = {
            "title": raw_title[:35],
            "meta": f"Yield: {raw_yields} • {raw_time} mins" if raw_time else f"Yield: {raw_yields}",
            "ingredients": clean_ingredients[:12],
            "steps": [convert_units_to_metric(s.split(". ")[0].strip()) for s in raw_instructions[:6]]
        }

    with open("current_recipe.json", "w") as f:
        json.dump(condensed, f, indent=2)

if __name__ == "__main__":
    recipe_url = os.environ.get("RECIPE_URL", "https://www.bbcgoodfood.com/recipes/best-ever-chocolate-brownies-recipe")
    parse_and_save(recipe_url)
