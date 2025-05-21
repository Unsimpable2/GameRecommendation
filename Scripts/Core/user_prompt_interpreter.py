import os
import sys
import json
import logging
import requests
import langdetect
from sentence_transformers import SentenceTransformer

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from Scripts.Database.check_excluded_titles import validate_excluded_titles

model = SentenceTransformer("BAAI/bge-base-en-v1.5")

def setup_logger(name, filename):
    log_dir = '../GameRecommendation/Logs/Prompt'
    os.makedirs(log_dir, exist_ok = True)
    log_file_path = os.path.join(log_dir, filename)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    handler = logging.FileHandler(log_file_path, mode = "a", encoding = "utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

prompt_logger = setup_logger("prompt_logger", "prompt_interpreter.log")
metadata_cleaner_logger = setup_logger("metadata_cleaner", "metadata_cleaner.log")

def is_english(text):
    try:
        lang = langdetect.detect(text)
        return lang == "en"
    except Exception as e:
        prompt_logger.error(f"Language detection error: {e}")
        return False

def is_prompt_too_long(prompt, model, max_tokens = 512):
    tokenized = model.tokenizer(prompt, return_tensors = "pt", truncation = False)
    return tokenized["input_ids"].shape[1] > max_tokens

def clean_json_fields(parsed_json):
    def clean_value(val):
        if val in ("", [], {}, "null", None):
            return None
        if isinstance(val, dict):
            return {k: clean_value(v) for k, v in val.items()}
        if isinstance(val, list):
            return [clean_value(v) for v in val if clean_value(v) is not None] or None
        return val

    return {k: clean_value(v) for k, v in parsed_json.items()}

def clean_metadata_fields(data, mapping_path = "../GameRecommendation/Data/DatabasGamesData/tags_genres_categories_map.json"):
    try:
        with open(mapping_path, "r", encoding = "utf-8") as f:
            mapping = json.load(f)
    except Exception as e:
        metadata_cleaner_logger.error(f"Error loading mapping file: {e}")
        return data

    cleaned = data.copy()

    for field in ["tags", "categories", "genres"]:
        input_list = data.get(field, [])
        valid_set = set(mapping.get(field, {}).values())
        normalized_map = {k.lower(): v for k, v in mapping.get(field, {}).items()}
        new_valid_items = []
        moved_items = []
        fallback_items = []

        for item in input_list or []:
            key = item.lower()
            if key in normalized_map:
                valid_value = normalized_map[key]
                if valid_value in valid_set:
                    new_valid_items.append(valid_value)
            else:
                moved = False
                for alt_field in ["tags", "categories", "genres"]:
                    if alt_field == field:
                        continue
                    alt_map = {k.lower(): v for k, v in mapping.get(alt_field, {}).items()}
                    if key in alt_map:
                        moved_value = alt_map[key]
                        metadata_cleaner_logger.info(f"Moved '{item}' from {field} to {alt_field}")
                        moved_items.append((alt_field, moved_value))
                        moved = True
                        break
                if not moved:
                    metadata_cleaner_logger.warning(f"Removed unrecognized value '{item}' from {field}")
                    fallback_items.append(item)

        cleaned[field] = sorted(set(new_valid_items)) if new_valid_items else None

        for alt_field, value in moved_items:
            cleaned.setdefault(alt_field, [])
            if value not in cleaned[alt_field]:
                cleaned[alt_field].append(value)

        for fallback in fallback_items:
            fallback_lower = fallback.lower()
            for alt_field in ["tags", "categories", "genres"]:
                possible_values = set(mapping.get(alt_field, {}).values())
                for val in possible_values:
                    if fallback_lower in val.lower() or val.lower() in fallback_lower:
                        metadata_cleaner_logger.info(f"Approximated '{fallback}' to '{val}' in {alt_field}")
                        cleaned.setdefault(alt_field, [])
                        if val not in cleaned[alt_field]:
                            cleaned[alt_field].append(val)
                        break

    return cleaned

def query_ollama(prompt, model = "mistral"):
    if not is_english(prompt):
        prompt_logger.warning("Prompt is not in English. Aborting request.")
        return None

    available_fields = {
    "is_free": "boolean (true or false)",
    "price": "float (0.0+)",
    "age_rating": "integer (PEGI-style age: 3, 7, 12, 16, 18) not a list, just single integer",
    "categories": "list of categories (e.g. 'Single-player', 'Co-op')",
    "tags": "list of tags (e.g. 'Fantasy', 'Open World')",
    "genres": "list of genres (e.g. 'RPG', 'Action')",
    "recommendations": "sentiment string or number of reviews (e.g. 'Very Positive', 'Mostly Negative')",
    "release_date": "date in format YYYY-MM-DD",
    "release_year": "integer (e.g. 2019, 2021)",
    "excluded_titles": (
        "List of game titles to exclude (text match). Always exclude all game titles explicitly mentioned in the prompt, "
        "even when used as positive comparisons or examples (e.g., 'like Dark Souls', 'similar to Divinity: Original Sin 2'). "
        "Include any game that is mentioned in the prompt — regardless if it's mentioned positively or negatively. "
        "The assumption is that the user already knows or played these games and wants recommendations excluding them. "
        "Examples: 'I'm looking for a game like Dark Souls, but not as difficult.' → excluded_titles: ['Dark Souls']"),
    "hardware_analysis": {
        "cpu_tier": "low / medium / high",
        "gpu_tier": "low / medium / high",
        "hardware_tier": "low / medium / high"
        }
    }

    detailed_prompt = f"""
        You are an intelligent filter parser for a video game recommendation engine.

        Below is the list of available fields and their types you can use to build filters:

        {json.dumps(available_fields, indent = 2)}

        Specific formatting rules:
        - If a user mentions a release year or relative time (e.g., "after 2019", "from the last 5 years"), convert it to an integer `release_year`.
        - For `recommendations`, use review sentiment from Steam such as: "Overwhelmingly Positive", "Very Positive", "Mostly Positive", "Mixed", "Negative", or a minimum numeric threshold (e.g., at least 1000 reviews).
        - `age_rating` must always be a single integer (e.g. 12, 16), not a list.
        - If `release_date` is mentioned in the prompt, extract only the year and use it in `release_year`.
        - If the user says the game should be “completely free”, set `is_free = true` and `price = null`.
        - If the user says the game should cost less than a certain amount (e.g. under 20 dollars), set `price` to that float value and **always** set `is_free = false`.
        - If both “free” and a price are mentioned (e.g. “free or under 20”), prefer `price` and set `is_free = false`.
        - For `excluded_titles`, extract all game titles mentioned in the prompt. This includes:
            • Games used as positive comparisons (e.g. “like Dark Souls”, “similar to Divinity: Original Sin 2”),
            • Games negatively referenced (e.g. “not like Fortnite”),
            • Any title directly mentioned.
            The assumption is that if a title is mentioned, the user already played it or knows it, and wants different suggestions. Always include these in `excluded_titles`.
        - Return **all** fields. If a field is not explicitly mentioned or inferable, return it with value `null`.

        Output strictly a valid JSON object — no extra text or commentary.

        User prompt:
        '{prompt}'
    """

    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": detailed_prompt,
        "stream": False
    }

    try:
        response = requests.post(url, json = data)
        response.raise_for_status()
        output = response.json().get("response", "").strip()
        prompt_logger.info(f"Prompt: {prompt}")
        return output
    except requests.RequestException as e:
        prompt_logger.error(f"HTTP error: {e}")
        return None
    except Exception as e:
        prompt_logger.error(f"Unexpected error: {e}")
        return None

def main():
    user_prompt = input("Enter your game recommendation prompt in English: ")

    if is_prompt_too_long(user_prompt, model):
        print("Your prompt is too long. Please shorten it to approximately 250–300 words.")
        prompt_logger.warning("Prompt too long. User asked to shorten it.")
        return

    result = query_ollama(user_prompt)
    if result:
        try:
            parsed = json.loads(result)
            cleaned = clean_json_fields(parsed)
            validated = clean_metadata_fields(cleaned)

            excluded_titles = validated.get("excluded_titles") or []
            valid_titles, invalid_titles = validate_excluded_titles(excluded_titles)
            validated["excluded_titles"] = valid_titles or None

            if invalid_titles:
                metadata_cleaner_logger.warning(f"Invalid excluded_titles (not found in DB): {invalid_titles}")
            if valid_titles:
                metadata_cleaner_logger.info(f"Valid excluded_titles (exist in DB): {valid_titles}")
            metadata_cleaner_logger.info("------------End of modification------------\n")

            print("\nCleaned & Validated JSON Response:\n", json.dumps(validated, indent=2))
            prompt_logger.info(f"Parsed + Cleaned + Validated JSON: {json.dumps(validated, indent=2)}")
        except json.JSONDecodeError as e:
            print("JSON parsing error.")
            prompt_logger.error(f"JSON decode error: {e}")
    else:
        print("\nNo response received. Check logs for details.")
    prompt_logger.info("------------End of prompt------------\n")

if __name__ == "__main__":
    main()