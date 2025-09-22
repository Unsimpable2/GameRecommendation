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

def embed_prompt(prompt_text):
    try:
        embedding = model.encode(prompt_text)
        return embedding.tolist()
    except Exception as e:
        prompt_logger.error(f"Error embedding prompt: {e}")
        return None

def clean_metadata_fields(data, mapping_path="../GameRecommendation/Data/DatabasGamesData/tags_genres_categories_map.json"):
    if not isinstance(data, dict):
        return {}

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)
    except Exception as e:
        metadata_cleaner_logger.error(f"Error loading mapping file: {e}")
        out = dict(data) if isinstance(data, dict) else {}
        for k in ["tags", "categories", "genres"]:
            if not isinstance(out.get(k), list):
                out[k] = []
        return out

    cleaned = data.copy()

    for field in ["tags", "categories", "genres"]:
        input_list = data.get(field, []) or []
        valid_set = set(mapping.get(field, {}).values())
        normalized_map = {str(k).lower(): v for k, v in mapping.get(field, {}).items()}

        new_valid_items = []
        moved_items = []
        fallback_items = []

        for item in input_list:
            if not isinstance(item, str):
                metadata_cleaner_logger.warning(f"{field}: non-string item skipped: {item!r}")
                continue

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
                    alt_map = {str(k).lower(): v for k, v in mapping.get(alt_field, {}).items()}
                    if key in alt_map:
                        moved_value = alt_map[key]
                        metadata_cleaner_logger.info(f"Moved '{item}' from {field} to {alt_field}")
                        moved_items.append((alt_field, moved_value))
                        moved = True
                        break
                if not moved:
                    metadata_cleaner_logger.warning(f"Removed unrecognized value '{item}' from {field}")
                    fallback_items.append(item)

        cleaned[field] = sorted(set(new_valid_items)) if new_valid_items else []

        for alt_field, value in moved_items:
            if not isinstance(cleaned.get(alt_field), list):
                cleaned[alt_field] = []
            if value not in cleaned[alt_field]:
                cleaned[alt_field].append(value)

        for fallback in fallback_items:
            if not isinstance(fallback, str):
                continue
            fallback_lower = fallback.lower()
            for alt_field in ["tags", "categories", "genres"]:
                possible_values = set(mapping.get(alt_field, {}).values())
                for val in possible_values:
                    if fallback_lower in val.lower() or val.lower() in fallback_lower:
                        metadata_cleaner_logger.info(
                            f"Approximated '{fallback}' to '{val}' in {alt_field}"
                        )
                        if not isinstance(cleaned.get(alt_field), list):
                            cleaned[alt_field] = []
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
    
def generate_sql_query_from_filters(filters, include_vector_similarity = False):
    params = {}
    progressive = []
    order_bonus = []
    base = []

    def add_clause(clauses, clause):
        if clause:
            clauses.append(clause)

    def any_descriptions_condition(jsonb_col, values, prefix):
        parts = []
        for i, v in enumerate(values):
            key = f"{prefix}_{i}"
            parts.append(f"EXISTS (SELECT 1 FROM jsonb_array_elements({jsonb_col}) elem WHERE elem->>'description' = %({key})s)")
            params[key] = v
        return "(" + " OR ".join(parts) + ")" if parts else None

    if filters.get("is_free") is not None:
        add_clause(base, "g.is_free = %(is_free)s")
        params["is_free"] = filters["is_free"]

    if filters.get("price") is not None and filters.get("is_free") is not True:
        add_clause(base, "g.price <= %(price)s")
        params["price"] = filters["price"]

    if filters.get("tags"):
        params["tags_any"] = filters["tags"]
        add_clause(
            base,
            "("
            "EXISTS (SELECT 1 FROM jsonb_array_elements_text(g.tags) t WHERE t = ANY(%(tags_any)s::text[])) "
            "OR g.tags ?| %(tags_any)s::text[]"
            ")"
        )

    if filters.get("excluded_titles"):
        add_clause(base, "NOT (g.excluded_titles @> %(excluded_titles)s::text[])")
        params["excluded_titles"] = filters["excluded_titles"]

    if filters.get("has_metacritic_score") is not None:
        add_clause(base, "g.has_metacritic_score = %(has_mc)s")
        params["has_mc"] = filters["has_metacritic_score"]

    base_conditions = " AND ".join(base) if base else "TRUE"

    release_year_clause = None
    if filters.get("release_year"):
        release_year_clause = "g.release_year >= %(release_year)s"
        params["release_year"] = filters["release_year"]
    
    rec_clause_strict = None
    if filters.get("recommendations"):
        rec = filters["recommendations"]
        if isinstance(rec, str):
            params["rec_sent"] = rec
            rec_clause_strict = (
                "jsonb_typeof(g.recommendations) = 'array' "
                "AND jsonb_array_length(g.recommendations) > 0 "
                "AND g.recommendations->>0 ILIKE %(rec_sent)s"
            )
        elif isinstance(rec, dict) and "min" in rec:
            params["min_reviews"] = rec["min"]
            rec_clause_strict = (
                "jsonb_typeof(g.recommendations) = 'array' "
                "AND jsonb_array_length(g.recommendations) > 1 "
                "AND (g.recommendations->>1) ~ '^[0-9]+$' "
                "AND (g.recommendations->>1)::int >= %(min_reviews)s"
            )

    if filters.get("genres"):
        add_clause(progressive, any_descriptions_condition("g.genres", filters["genres"], "genre"))

    if filters.get("categories"):
        add_clause(progressive, any_descriptions_condition("g.categories", filters["categories"], "cat"))

    mid_conditions = " AND ".join([c for c in [base_conditions, release_year_clause, any_descriptions_condition("g.genres", filters.get("genres", []), "m_genre")] if c]) or base_conditions
    strict_conditions = " AND ".join([c for c in [base_conditions, release_year_clause, rec_clause_strict, *progressive] if c]) or "TRUE"

    hw = filters.get("hardware_analysis") or {}
    if hw.get("hardware_tier"):
        order_bonus.append(f"(g.hardware_analysis->>'hardware_tier' = %(ob_hw_tier)s) DESC")
        params["ob_hw_tier"] = hw["hardware_tier"]
    if hw.get("cpu_tier"):
        order_bonus.append(f"(g.hardware_analysis->>'cpu_tier' = %(ob_cpu_tier)s) DESC")
        params["ob_cpu_tier"] = hw["cpu_tier"]
    if hw.get("gpu_tier"):
        order_bonus.append(f"(g.hardware_analysis->>'gpu_tier' = %(ob_gpu_tier)s) DESC")
        params["ob_gpu_tier"] = hw["gpu_tier"]

    if filters.get("release_year"):
        order_bonus.append("(g.release_year >= %(release_year)s) DESC")

    if filters.get("bonus_tags"):
        ors = " OR ".join([f"g.tags ? %({f'bt_{i}'})s" for i, _ in enumerate(filters["bonus_tags"])])
        for i, t in enumerate(filters["bonus_tags"]):
            params[f"bt_{i}"] = t
        order_bonus.append(f"(({ors})) DESC")

    if filters.get("age_rating"):
        order_bonus.append("(g.age_rating >= %(age_rating)s) DESC")
        params["age_rating"] = filters["age_rating"]

    order_bonus.append("(jsonb_typeof(g.recommendations)='array' " "AND g.recommendations->>0 ILIKE ANY (ARRAY['Overwhelmingly Positive','Very Positive'])) DESC")
    order_bonus.append("CASE WHEN jsonb_typeof(g.recommendations)='array' ""AND (g.recommendations->>1) ~ '^[0-9]+$' ""THEN (g.recommendations->>1)::int ELSE 0 END DESC")

    order_tail = (", " + ", ".join(order_bonus)) if order_bonus else ""

    if include_vector_similarity:
        params["prompt_vector"] = filters["prompt_vector"]
        params["similarity_threshold"] = filters.get("similarity_threshold", 0.70)

        query = f"""
        WITH q AS (
            SELECT %(prompt_vector)s::vector(768) AS v
        ),
        strict AS (
            SELECT g.app_id, g.game_name, 1 - (g.metadata_vector <=> q.v) AS similarity
            FROM games g, q
            WHERE {strict_conditions}
              AND 1 - (g.metadata_vector <=> q.v) >= %(similarity_threshold)s
            ORDER BY similarity DESC NULLS LAST{order_tail}
            LIMIT 3
        ),
        have_strict AS (SELECT (COUNT(*) > 0) AS has_rows FROM strict),

        mid AS (
            SELECT g.app_id, g.game_name, 1 - (g.metadata_vector <=> q.v) AS similarity
            FROM games g, q
            WHERE {mid_conditions}
            ORDER BY similarity DESC NULLS LAST{order_tail}
            LIMIT 3
        ),
        have_mid AS (SELECT (COUNT(*) > 0) AS has_rows FROM mid)

        SELECT * FROM strict
        UNION ALL
        SELECT * FROM mid WHERE NOT (SELECT has_rows FROM have_strict)
        UNION ALL
        SELECT * FROM (
            SELECT g.app_id, g.game_name, 1 - (g.metadata_vector <=> q.v) AS similarity
            FROM games g, q
            WHERE {base_conditions}
            ORDER BY similarity DESC NULLS LAST{order_tail}
            LIMIT 3
        ) base
        WHERE NOT (SELECT has_rows FROM have_strict) AND NOT (SELECT has_rows FROM have_mid);
        """
    else:
        query = f"""
        SELECT g.app_id, g.game_name
        FROM games g
        WHERE {strict_conditions}
        ORDER BY game_name ASC
        LIMIT 3;
        """

    return query.strip(), params

def adjust_similarity_threshold(base_query_func, filters, db_execute_func, initial_threshold = 0.70, min_results = 3):
    threshold = initial_threshold
    while threshold >= 0.50:
        filters["similarity_threshold"] = threshold
        query, params = base_query_func(filters, include_vector_similarity = True)
        result_count = db_execute_func(query, params)
        if result_count >= min_results:
            return query, params, threshold
        threshold -= 0.05

    return query, params, threshold

def fake_execute(query, params):
    return 0

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
            validated = clean_metadata_fields(cleaned) or {}

            excluded_titles = validated.get("excluded_titles") or []
            valid_titles, invalid_titles = validate_excluded_titles(excluded_titles)
            validated["excluded_titles"] = valid_titles or None

            user_vector = embed_prompt(user_prompt)
            if not user_vector:
                print("Could not generate prompt embedding.")
                return

            validated["prompt_vector"] = user_vector

            sql_query, sql_params, final_threshold = adjust_similarity_threshold(
                generate_sql_query_from_filters,
                validated,
                fake_execute  #TODO, database connection/script
            )

            print(f"\nFinal similarity threshold used: {final_threshold}")
            print("\nGenerated SQL Query:")
            print(sql_query)
            print("\nWith parameters:")
            print(sql_params)

            if invalid_titles:
                metadata_cleaner_logger.warning(f"Invalid excluded_titles (not found in DB): {invalid_titles}")
            if valid_titles:
                metadata_cleaner_logger.info(f"Valid excluded_titles (exist in DB): {valid_titles}")
            metadata_cleaner_logger.info("------------End of modification------------\n")

            prompt_logger.info(f"Parsed + Cleaned + Validated JSON: {json.dumps(validated, indent = 2)}")
        except json.JSONDecodeError as e:
            prompt_logger.error(f"JSON decode error: {e}")
    else:
        print("\nNo response received. Check logs for details.")
    prompt_logger.info("------------End of prompt------------\n")

if __name__ == "__main__":
    main()