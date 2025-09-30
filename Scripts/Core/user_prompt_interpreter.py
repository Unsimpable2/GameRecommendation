import os
import re
import sys
import json
import logging
import requests
import langdetect
from sentence_transformers import SentenceTransformer

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from Scripts.Database.prompt_to_database import run_sql
from Scripts.Database.check_excluded_titles import validate_excluded_titles

model = SentenceTransformer("BAAI/bge-base-en-v1.5")

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
OSC8_OPEN_RE  = re.compile(r"\x1b]8;;.*?\x1b\\")
OSC8_CLOSE_RE = re.compile(r"\x1b]8;;\x1b\\")

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

def clean_metadata_fields(data, mapping_path="../GameRecommendation/Data/DatabaseGamesData/tags_genres_categories_map.json"):
    if not isinstance(data, dict):
        return {}

    try:
        with open(mapping_path, "r", encoding = "utf-8") as f:
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

def query_ollama(prompt, model = "mistral", mapping_path = "../GameRecommendation/Data/DatabaseGamesData/tags_genres_categories_map.json"):
    if not is_english(prompt):
        prompt_logger.warning("Prompt is not in English. Aborting request.")
        return None

    allowed_tags = []
    allowed_genres = []
    allowed_categories = []

    try:
        with open(mapping_path, "r", encoding = "utf-8") as f:
            mapping = json.load(f) or {}
            allowed_tags = sorted(set(mapping.get("tags", {}).values()))
            allowed_genres = sorted(set(mapping.get("genres", {}).values()))
            allowed_categories = sorted(set(mapping.get("categories", {}).values()))
    except Exception as e:
        metadata_cleaner_logger.error(f"Error loading mapping file for LLM prompt: {e}")

    available_fields = {
        "is_free": "boolean",
        "price": "float (0.0+) or null (must be null when is_free = true)",
        "age_rating": "integer (PEGI: 3, 7, 12, 16, 18) or null",
        "categories": "list of categories (choose from allowed list if provided)",
        "tags": "list of tags (choose from allowed list if provided)",
        "genres": "list of genres (choose from allowed list if provided)",
        "recommendations": "string sentiment (e.g. 'Very Positive') OR object { 'sentiment': 'Very Positive', 'min': 1000 } or null",
        "release_date": "date YYYY-MM-DD or null",
        "release_year": "integer year or null",
        "excluded_titles": "list of strings (game titles) or []",
        "hardware_analysis": {
            "cpu_tier": "low/medium/high or null",
            "gpu_tier": "low/medium/high or null",
            "hardware_tier": "low/medium/high or null"
        }
    }

    available_fields_json = esc_braces(json.dumps(available_fields, indent = 2))
    schema_block = esc_braces("""
        OUTPUT SCHEMA (return these keys, including *_evidence lists):
        {
          "is_free": bool or null,
          "is_free_evidence": [string],
          "price": float or null,
          "price_evidence": [string],
          "age_rating": int or null,
          "age_rating_evidence": [string],
          "categories": [string],
          "categories_evidence": [string],
          "tags": [string],
          "tags_evidence": [string],
          "genres": [string],
          "genres_evidence": [string],
          "recommendations": string or { "sentiment": string, "min": int } or null,
          "recommendations_evidence": [string],
          "release_date": string or null,
          "release_date_evidence": [string],
          "release_year": int or null,
          "release_year_evidence": [string],
          "excluded_titles": [string],
          "excluded_titles_evidence": [string],
          "hardware_analysis": {
            "cpu_tier": "low"|"medium"|"high"|null,
            "gpu_tier": "low"|"medium"|"high"|null,
            "hardware_tier": "low"|"medium"|"high"|null
          },
          "hardware_analysis_evidence": [string]
        }
        """)
    
    schema_block = esc_braces(schema_block)

    rules = f"""
        You are an information extractor for a Steam game recommender.
        Return a SINGLE valid JSON object. NO extra text.

        Mapping rules (must):
        - Scan the prompt for literal mentions or common abbreviations. Then map to the CLOSEST item from the allowed lists using:
          • case-insensitive exact match,
          • case-insensitive substring,
          • known abbreviations: "RPG": "role-playing", "RTS": "real-time strategy", "MMO": "massively multiplayer".
        - If the prompt contains “co-op”, “coop”, “co op”, map to the category whose name contains “co-op” (e.g., “Co-op” or “Online Co-Op”) if present in ALLOWED_CATEGORIES.
        - If the prompt contains “RPG” or “role-playing”, map to the genre entry that contains “RPG” or “Role-Playing” from ALLOWED_GENRES.
        - Do not invent labels outside the allowed lists. If no allowed item fits with evidence, leave [].
        - If the prompt says “after <YEAR>”, set `release_year` to YEAR+1.
        - If the prompt says “like <Title>” or “not like <Title>”, include <Title> in `excluded_titles`.

        Mapping guidance:
        - Categories are modes/features like "Co-op", "Single-player", "Multi-player".
        - Tags are thematic/descriptor labels like "Fantasy", "Story Rich", "Open World".
        - Genres are broad types like "RPG", "Action", "Strategy".
        Always map accordingly and do not place thematic tags under categories.

        1) ALWAYS return ALL fields from the schema with values first.
           - If a field cannot be inferred from the prompt, set it to null (or [] for lists).
           - Never skip fields. Never invent new keys.

        2) ALSO return a corresponding *_evidence array for EVERY field.
           - Evidence must be exact words/phrases from the prompt that justify the chosen value.
           - If no evidence exists, return [] but keep the value (or null if not inferable).

        3) Vocabulary mapping (do NOT hardcode any specific labels):
           - You are given allowed lists (tags, genres, categories). Choose the CLOSEST canonical value
             using semantic matching. If nothing fits with evidence, leave the list [].
           - ALLOWED_TAGS: {allowed_tags if allowed_tags else "[]"}
           - ALLOWED_GENRES: {allowed_genres if allowed_genres else "[]"}
           - ALLOWED_CATEGORIES: {allowed_categories if allowed_categories else "[]"}

           Normalization rules:
           - Hardware tiers: map any “mid”, “mid-tier”, “medium-tier” → "medium"; “high-end” → "high"; “low-end” → "low".
           - Age rating: extract PEGI number as integer if stated (e.g., “PEGI 16” → 16).
           - Trim whitespace; deduplicate lists; keep canonical casing from allowed lists.

        4) Reviews:
           - `recommendations` can be a string (one of: "Overwhelmingly Positive","Very Positive","Mostly Positive","Mixed","Negative")
             OR an object {{ "sentiment": <one of the above>, "min": <integer> }} if the prompt implies a minimum review count/“high reviews”.
           - If the prompt implies strong positivity but no exact phrase, pick the closest sentiment and include evidence.

        5) Conflicts:
           - If both “free” and a price ceiling appear, prefer price and set is_free=false, price=<ceiling>.
           - If only “free” appears, set is_free=true and price=null.

        6) Time:
           - Convert phrases like “after 2019”, “since 2020”, “past 5 years” to integer `release_year`.

        7) Titles:
           - Include ALL explicitly named games in `excluded_titles` (even if used as positive/negative examples, or “like <title>”).
           - Keep exact spelling from the prompt.

        8) Output format:
        {json.dumps(available_fields_json, indent = 2)}

        Available fields schema (for reference):
        {schema_block}

        Return ONLY a valid JSON object conforming to the OUTPUT SCHEMA above.
    """

    detailed_prompt = (
        rules
        + "\nUSER PROMPT:\n"
        + repr(prompt)
        + "\nRETURN ONLY JSON.\n"
    )

    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": detailed_prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,
            "top_p": 0.9,
            "num_ctx": 4096
        }
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

def esc_braces(s: str) -> str:
    return s.replace("{", "{{").replace("}", "}}")
    
def prune_by_evidence(extracted: dict) -> dict:
    if not isinstance(extracted, dict):
        return extracted

    pruned = dict(extracted)

    list_pairs = [
        ("tags", "tags_evidence"),
        ("genres", "genres_evidence"),
        ("categories", "categories_evidence"),
        ("excluded_titles", "excluded_titles_evidence"),
    ]
    for field, ev in list_pairs:
        vals = pruned.get(field) or []
        evi  = pruned.get(ev) or []
        if not evi:
            pruned[field] = []

    single_pairs = [
        ("is_free", "is_free_evidence"),
        ("price", "price_evidence"),
        ("age_rating", "age_rating_evidence"),
        ("release_year", "release_year_evidence"),
        ("release_date", "release_date_evidence"),
        ("recommendations", "recommendations_evidence"),
        ("hardware_analysis", "hardware_analysis_evidence"),
    ]
    for field, ev in single_pairs:
        evi = pruned.get(ev) or []
        if not evi:
            pruned[field] = None

    return pruned

def backfill_from_prompt(prompt, obj, allowed_tags, allowed_genres, allowed_categories):
    text = (prompt or "")
    p = text.lower()

    for k in ("tags", "genres", "categories"):
        if not isinstance(obj.get(k), list):
            obj[k] = obj.get(k) or []

    def norm(s: str) -> str:
        s = s.lower().replace("-", " ")
        s = re.sub(r"[^a-z0-9\s]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    tokens = norm(text).split()
    ngrams = set()
    for n in (1, 2, 3):
        for i in range(len(tokens) - n + 1):
            ngrams.add(" ".join(tokens[i:i+n]))

    def find_evidence_phrase(canonical: str):
        pattern = re.compile(re.escape(canonical), re.IGNORECASE)
        m = pattern.search(text)
        return m.group(0) if m else canonical

    def add_from_allowed(allowed_list, current_list, ev_key):
        base_key = ev_key[:-9] if ev_key.endswith("_evidence") else ev_key

        if current_list:
            return

        picked = []
        for label in (allowed_list or []):
            nlabel = norm(label)
            if not nlabel:
                continue
            if nlabel in ngrams:
                picked.append(label)

        if not picked:
            return

        obj[base_key] = sorted(set(picked))
        if not isinstance(obj.get(ev_key), list):
            obj[ev_key] = []

        for lbl in obj[base_key]:
            ev = find_evidence_phrase(lbl)
            if ev:
                obj[ev_key].append(ev)

    add_from_allowed(allowed_tags, obj["tags"], "tags_evidence")
    add_from_allowed(allowed_genres, obj["genres"], "genres_evidence")
    add_from_allowed(allowed_categories, obj["categories"], "categories_evidence")

    if not obj.get("release_year"):
        m = re.search(r"\bafter\s+(\d{4})\b", p)
        if m:
            yr = int(m.group(1)) + 1
            obj["release_year"] = yr
            obj.setdefault("release_year_evidence", []).append(m.group(0))
        else:
            m2 = re.search(r"\bsince\s+(\d{4})\b", p)
            if m2:
                yr = int(m2.group(1))
                obj["release_year"] = yr
                obj.setdefault("release_year_evidence", []).append(m2.group(0))

    def infer_excluded_titles(text: str):
        found = []
        evid = []
        patterns = [r"(?:like|similar to|not like|excluding|other than|different from)\s+([A-Z][^\.;,\n]+)", r"\"([^\"]+)\""]
        
        for pat in patterns:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                chunk = m.group(1).strip()
                chunk = re.split(r"[.;,()]\s*", chunk)[0].strip()
                candidate = " ".join(chunk.split()[:6]).strip()
                if len(candidate) >= 2:
                    found.append(candidate)
                    evid.append(m.group(0).strip())
        seen = set(); uniq = []
        for t in found:
            if t.lower() not in seen:
                seen.add(t.lower()); uniq.append(t)
        return uniq, evid

    if not obj.get("excluded_titles"):
        titles_raw, evid = infer_excluded_titles(prompt)
        try:
            valid, _invalid = validate_excluded_titles(titles_raw)
        except Exception:
            valid = titles_raw
    
        if valid:
            obj["excluded_titles"] = valid
            obj["excluded_titles_evidence"] = evid
    
        hw = obj.get("hardware_analysis") or {}
        def normalize_tier(val):
            if not val:
                return val
            v = val.lower()
            if any(x in v for x in ["mid", "medium"]):
                return "medium"
            if "high" in v:
                return "high"
            if "low" in v:
                return "low"
            return val
    
        changed = False
        for k in ("cpu_tier", "gpu_tier", "hardware_tier"):
            if k in hw and hw[k]:
                nv = normalize_tier(hw[k])
                if nv != hw[k]:
                    hw[k] = nv
                    changed = True
        if hw and changed:
            obj["hardware_analysis"] = hw
    
        obj["tags"] = sorted(set(obj.get("tags") or []))
        obj["genres"] = sorted(set(obj.get("genres") or []))
        obj["categories"] = sorted(set(obj.get("categories") or []))
    
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
        add_clause(base, "(""EXISTS (SELECT 1 FROM jsonb_array_elements_text(g.tags) t WHERE t = ANY(%(tags_any)s::text[])) ""OR g.tags ?| %(tags_any)s::text[]"")")

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
            rec_clause_strict = ("jsonb_typeof(g.recommendations) = 'array' " "AND jsonb_array_length(g.recommendations) > 0 ""AND g.recommendations->>0 ILIKE %(rec_sent)s")
        elif isinstance(rec, dict) and "min" in rec:
            params["min_reviews"] = rec["min"]
            rec_clause_strict = ("jsonb_typeof(g.recommendations) = 'array' " "AND jsonb_array_length(g.recommendations) > 1 " "AND (g.recommendations->>1) ~ '^[0-9]+$' " "AND (g.recommendations->>1)::int >= %(min_reviews)s")

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

def db_execute_count(query, params):
    q = query.rstrip(" \t\r\n;")
    count_sql = f"SELECT COUNT(*) AS n FROM ({q}) subq"
    row = run_sql(count_sql, params, fetch = "one", as_dict = True)
    return row["n"] if row and "n" in row else 0

def _strip_invisible(s):
    if not isinstance(s, str):
        s = str(s)
    s = OSC8_OPEN_RE.sub("", s)
    s = OSC8_CLOSE_RE.sub("", s)
    s = ANSI_RE.sub("", s)
    return s

def _visible_len(s):
    return len(_strip_invisible(s))

def pad_visible(s, width):
    pad = width - _visible_len(s)
    if pad > 0:
        return s + " " * pad
    return s

def print_table(rows, max_rows = 20, use_hyperlinks = True):
    if not rows:
        print("\n--- No results ---")
        return

    headers = ["game_name", "app_id", "similarity"]
    header_labels = {
        "game_name": "Game Title",
        "app_id":   "Steam AppID",
        "similarity": "Score",
    }

    def steam_link_cell(app_id):
        url = f"https://store.steampowered.com/app/{app_id}"
        if use_hyperlinks:
            return f"\x1b]8;;{url}\x1b\\{app_id}\x1b]8;;\x1b\\"
        else:
            return str(app_id)

    data = []
    for r in rows[:max_rows]:
        sim = r.get("similarity", "")
        if isinstance(sim, float):
            sim = f"{sim:.6f}"
        data.append({
            "game_name": str(r.get("game_name", "")),
            "app_id": steam_link_cell(r.get("app_id", "")),
            "similarity": sim,
        })

    col_w = {h: _visible_len(header_labels[h]) for h in headers}
    for row in data:
        for h in headers:
            col_w[h] = max(col_w[h], _visible_len(str(row[h])))

    def fmt_row(row_dict):
        return " | ".join(pad_visible(str(row_dict[h]), col_w[h]) for h in headers)

    print()
    print(" | ".join(pad_visible(header_labels[h], col_w[h]) for h in headers))
    print("-+-".join("-" * col_w[h] for h in headers))
    for row in data:
        print(fmt_row(row))

    if len(rows) > max_rows:
        print(f"... and {len(rows) - max_rows} more rows")

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
            
            mapping_path = "../GameRecommendation/Data/DatabaseGamesData/tags_genres_categories_map.json"
            try:
                with open(mapping_path, "r", encoding = "utf-8") as f:
                    _mapping = json.load(f) or {}
                    allowed_tags = sorted(set((_mapping.get("tags") or {}).values()))
                    allowed_genres = sorted(set((_mapping.get("genres") or {}).values()))
                    allowed_categories = sorted(set((_mapping.get("categories") or {}).values()))
            except Exception:
                allowed_tags = []
                allowed_genres = []
                allowed_categories = []

            backfill_from_prompt(user_prompt, cleaned, allowed_tags, allowed_genres, allowed_categories)

            validated = clean_metadata_fields(cleaned) or {}
            validated = prune_by_evidence(validated)

            excluded_titles = validated.get("excluded_titles") or []
            valid_titles, invalid_titles = validate_excluded_titles(excluded_titles)
            validated["excluded_titles"] = valid_titles or None

            user_vector = embed_prompt(user_prompt)
            if not user_vector:
                print("Could not generate prompt embedding.")
                return

            validated["prompt_vector"] = user_vector

            sql_query, sql_params, final_threshold = adjust_similarity_threshold(generate_sql_query_from_filters, validated, db_execute_count)

            rows = run_sql(sql_query, sql_params, fetch = "all", as_dict = True)
            print("\n--- Query results ---")
            print_table(rows, max_rows = 3, use_hyperlinks = True) 

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