import os
import json
import re
import requests
from recipe_scrapers import scrape_html

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

def parse_and_save(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    # Use scrape_html with the fetched HTML
    scraper = scrape_html(response.text, org_url=url)

    title = scraper.title()
    yields = scraper.yields()
    total_time = scraper.total_time()

    raw_ingredients = scraper.ingredients()
    raw_instructions = scraper.instructions_list()

    clean_ingredients = [convert_units_to_metric(i.strip()) for i in raw_ingredients if i.strip()]

    summary_steps = []
    for step in raw_instructions:
        cleaned = convert_units_to_metric(step.strip())
        if cleaned:
            first_sentence = cleaned.split(". ")[0].rstrip(".")
            if len(first_sentence) > 95:
                first_sentence = first_sentence[:92] + "..."
            summary_steps.append(first_sentence)

    recipe_payload = {
        "title": title[:38],
        "meta": f"Yield: {yields}  •  {total_time} mins" if total_time else f"Yield: {yields}",
        "ingredients": clean_ingredients[:14],
        "steps": summary_steps[:6]
    }

    with open("current_recipe.json", "w") as f:
        json.dump(recipe_payload, f, indent=2)

if __name__ == "__main__":
    recipe_url = os.environ.get("RECIPE_URL", "https://www.bbcgoodfood.com/recipes/best-ever-chocolate-brownies-recipe")
    parse_and_save(recipe_url)
