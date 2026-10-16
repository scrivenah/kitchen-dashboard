import os
import json
import requests
from recipe_scrapers import scrape_html
from google import genai

def condense_with_gemini(raw_title, raw_yields, raw_time, raw_ingredients, raw_instructions):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not found; falling back to raw truncation.")
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
1. "title": Shortened title under 35 characters.
2. "meta": Concise summary like "Serves 4 • 45 mins".
3. "ingredients": List of essential ingredients. Convert all units to metric (grams, ml, °C). Max 12 items.
4. "steps": Exactly 5 to 6 concise, numbered action steps. Each step MUST be under 20 words, but keep vital temperatures, pan sizes, and baking times. Fix any weird website scraper text.

Output strictly valid JSON matching this schema:
{{
  "title": "...",
  "meta": "...",
  "ingredients": ["...", "..."],
  "steps": ["...", "..."]
}}
"""

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )
    return json.loads(response.text)

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

    # Condense cleanly using free Gemini Flash
    condensed = condense_with_gemini(raw_title, raw_yields, raw_time, raw_ingredients, raw_instructions)

    if not condensed:
        # Fallback if API key is missing
        condensed = {
            "title": raw_title[:35],
            "meta": f"Yield: {raw_yields} • {raw_time} mins" if raw_time else f"Yield: {raw_yields}",
            "ingredients": [i.strip() for i in raw_ingredients[:12]],
            "steps": [s.split(". ")[0].strip() for s in raw_instructions[:6]]
        }

    with open("current_recipe.json", "w") as f:
        json.dump(condensed, f, indent=2)

if __name__ == "__main__":
    recipe_url = os.environ.get("RECIPE_URL", "https://www.bbcgoodfood.com/recipes/best-ever-chocolate-brownies-recipe")
    parse_and_save(recipe_url)
