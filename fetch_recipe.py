import os
import sys
import json
import time
import re
from urllib.parse import urlparse

try:
    from curl_cffi import requests as c_requests
except ImportError:
    import requests as c_requests

from recipe_scrapers import scrape_html
from google import genai

def extract_instagram_caption(insta_url):
    """Extracts caption text from an Instagram post or reel via public embed."""
    match = re.search(r'instagram\.com/(?:p|reel|reels)/([^/?#&]+)', insta_url)
    if not match:
        raise ValueError("Could not parse Instagram post/reel ID.")
    
    shortcode = match.group(1)
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    print(f"Fetching Instagram embed: {embed_url}")

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }

    try:
        resp = c_requests.get(embed_url, headers=headers, impersonate="chrome120", timeout=15)
    except TypeError:
        resp = c_requests.get(embed_url, headers=headers, timeout=15)

    resp.raise_for_status()

    caption_match = re.search(r'class="Caption"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
    if not caption_match:
        caption_match = re.search(r'<div class="CaptionText"[^>]*>(.*?)</div>', resp.text, re.DOTALL)

    if caption_match:
        raw_html = caption_match.group(1)
        text = re.sub(r'<br\s*/?>', '\n', raw_html)
        text = re.sub(r'<.*?>', '', text)
        return text.strip()

    cleaned = re.sub(r'<[^>]+>', ' ', resp.text)
    return cleaned[:4000]

def condense_with_gemini(recipe_url, raw_title, raw_yields, raw_time, raw_ingredients, raw_instructions, raw_raw_text=""):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable is missing or empty!")
        return None

    client = genai.Client(api_key=api_key)

    if raw_raw_text:
        content_context = f"""
Raw Text/Caption from Recipe or Social Post:
{raw_raw_text}
"""
    else:
        content_context = f"""
Recipe: {raw_title}
Yield: {raw_yields}
Time: {raw_time}

Raw Ingredients:
{chr(10).join(raw_ingredients)}

Raw Steps:
{chr(10).join(raw_instructions)}
"""

    prompt = f"""
You are an expert chef's assistant formatting a recipe for an 800x480 e-paper kitchen display.
Your job is to condense the recipe so it fits on a SINGLE screen with zero fluff.

Source URL / Site: {recipe_url}
{content_context}

Requirements:
1. "title": Include author/publication attribution in possessive form, followed by the specific recipe name (e.g. "RecipeTin's BBQ Pork Ribs", "Lulu's Beef & Broccoli Fried Rice"). Keep under 40 characters.
2. "meta": Concise summary like "Serves 4 • 585 kcal • 25 mins" or "Yield: 12 • ~420 kcal • 35m".
   - If calorie counts or energy per serving are in the source, include them.
   - If no calorie count is provided, calculate an informed estimation per serving based on total ingredients and yield, prefixing with a tilde (e.g. "~540 kcal"). Keep entire meta string under 32 characters.
3. "ingredients": Exactly 5 to 8 grouped component items.
   - GROUP LOGICAL COMPONENTS: Whenever there is a marinade, sauce, batter, dressing, or base, combine those items onto ONE line with their exact measurements (e.g. "Sauce: 2 tbsp oyster sauce, 2 tbsp soy, 1 tbsp Shaoxing wine").
   - DO NOT REPEAT LABELS: Never split the same category across multiple separate bullet points.
   - METRIC CONVERSIONS: Convert weights to grams (g/kg), volumes to ml/tbsp/tsp, and oven temps to °C.
   - PRESERVE QUANTITIES: Keep exact measurements for every item inside the group.
4. "steps": Exactly 5 to 6 concise action steps WITHOUT leading numbers.
   - HARDWARE CONVERSIONS: Convert pan/dish dimensions from inches to cm.
   - LENGTH & FLOW: Complete imperative sentences (max 120 characters per step).
   - CRITICAL PRECISION: Retain key pan temps, heat settings, and cooking times.

Output strictly valid JSON matching this schema:
{{
  "title": "...",
  "meta": "...",
  "ingredients": ["...", "..."],
  "steps": ["...", "..."]
}}
"""

    candidate_models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
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
                
                if "steps" in data:
                    data["steps"] = [re.sub(r'^\d+[\.\)]\s*', '', s) for s in data["steps"]]

                print(f"SUCCESS: Gemini ({model_name}) condensed recipe successfully!")
                return data
            except Exception as e:
                err_msg = str(e)
                print(f"Warning: {model_name} failed with: {err_msg}")
                if "503" in err_msg or "UNAVAILABLE" in err_msg:
                    time.sleep(2)
                    continue
                break

    print("All AI attempts exhausted.")
    return None

def parse_and_save(recipe_url):
    print(f"Processing recipe from: {recipe_url}")
    parsed = urlparse(recipe_url)
    
    # Instagram URLs
    if "instagram.com" in parsed.netloc:
        print("Detected Instagram URL. Extracting caption...")
        try:
            caption = extract_instagram_caption(recipe_url)
            print(f"Extracted {len(caption)} characters of caption text.")
        except Exception as e:
            print(f"Failed to extract Instagram caption: {e}")
            sys.exit(1)

        condensed = condense_with_gemini(
            recipe_url,
            raw_title="",
            raw_yields="",
            raw_time="",
            raw_ingredients=[],
            raw_instructions=[],
            raw_raw_text=caption
        )
    # Standard Web Pages (with wild_mode and raw text fallback)
    else:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
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
            response = c_requests.get(recipe_url, headers=headers, impersonate="chrome120", timeout=15)
        except TypeError:
            response = c_requests.get(recipe_url, headers=headers, timeout=15)
            
        response.raise_for_status()

        condensed = None
        try:
            scraper = scrape_html(html=response.text, org_url=recipe_url, wild_mode=True)
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

            if raw_ingredients and raw_instructions:
                condensed = condense_with_gemini(
                    recipe_url, raw_title, raw_yields, raw_time, raw_ingredients, raw_instructions
                )
        except Exception as e:
            print(f"recipe-scrapers wild mode could not parse structured schema: {e}")

        # Fallback to direct text scraping if structured parser produced nothing
        if not condensed:
            print("Falling back to raw HTML AI extraction...")
            clean_html = re.sub(r'<(script|style).*?</\1>', '', response.text, flags=re.DOTALL | re.IGNORECASE)
            plain_text = re.sub(r'<[^>]+>', ' ', clean_html)
            plain_text = re.sub(r'\s+', ' ', plain_text).strip()[:8000]

            condensed = condense_with_gemini(
                recipe_url,
                raw_title="",
                raw_yields="",
                raw_time="",
                raw_ingredients=[],
                raw_instructions=[],
                raw_raw_text=plain_text
            )

    if not condensed:
        print("ERROR: Failed to generate condensed recipe data.")
        sys.exit(1)

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
