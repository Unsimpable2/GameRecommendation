import os
import re
import json
import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "Data", "ComponentsData")
CPU_BENCHMARK_PATH = os.path.join(DATA_DIR, "benchmark_cpu.jsonl")
GPU_BENCHMARK_PATH = os.path.join(DATA_DIR, "benchmark_gpu.jsonl")

model = SentenceTransformer("BAAI/bge-base-en-v1.5")
VECTOR_SIZE = 768

def round_vector(vector, precision = 4, target_length = VECTOR_SIZE):
    rounded = [round(x, precision) for x in vector]
    return rounded[:target_length] + [0.0] * (target_length - len(rounded))

def process_text_to_vector(text):
    vector = model.encode(text).tolist()
    return round_vector(vector)

def create_metadata_string(game_data):
    tags = ", ".join(game_data.get("Tags", []))
    genres = ", ".join([g.get("description", "") for g in game_data.get("Genres", [])])
    categories = ", ".join([c.get("description", "") for c in game_data.get("Categories", [])])
    return f"Tags: {tags}. Genres: {genres}. Categories: {categories}."

def generate_feature_vector(game_data, all_tags, all_genres):
    tag_vector = np.zeros(len(all_tags))
    for tag in game_data.get("Tags", []):
        if tag in all_tags:
            tag_vector[all_tags.index(tag)] = 1

    genre_vector = np.zeros(len(all_genres))
    for genre in game_data.get("Genres", []):
        desc = genre.get("description", "")
        if desc in all_genres:
            genre_vector[all_genres.index(desc)] = 1

    recommendations = game_data.get("Recommendations", 0)
    try:
        recommendations_normalized = int(recommendations) / 100000
    except (ValueError, TypeError):
        recommendations_normalized = 0

    feature_vector = np.concatenate([tag_vector, genre_vector, [recommendations_normalized]])
    return round_vector(feature_vector)

def load_component_scores(path):
    scores = {}
    with open(path, "r", encoding = "utf-8") as f:
        for line in f:
            obj = json.loads(line)
            scores[obj["name"].lower()] = obj["score"]
    return scores

def clean_requirements_text(text):
    if not text:
        return ""
    text = re.sub(r"^\s*minimum:\s*", "", text, flags = re.IGNORECASE)
    text = re.sub(r"^\s*recommended:\s*", "", text, flags = re.IGNORECASE)
    return text.strip()

def extract_release_year(date):
    if not date or "no information" in date.lower(): return None
    for fmt in ("%d %b, %Y", "%Y-%m-%d", "%b %Y"):
        try: return datetime.strptime(date.strip(), fmt).year
        except: continue
    match = re.search(r"\b(19|20)\d{2}\b", date)
    return int(match.group(0)) if match else None

def has_metacritic_score(meta):
    try: return int(meta) and True
    except: return False

def compute_vector_norm(vector):
    return float(np.linalg.norm(vector)) if isinstance(vector, list) else 0.0

def parse_requirements(req):
    req = req.lower()
    ram = dx = storage_gb = None

    for pat in [r"(\d{1,3}) ?gb ram", r"ram:? (\d{1,3}) ?gb"]:
        m = re.search(pat, req)
        if m: ram = int(m.group(1)); break

    for pat in [r"directx[^\d]{0,10}(\d{1,2})", r"dx(?:version)?[^\d]{0,5}(\d{1,2})"]:
        m = re.search(pat, req)
        if m: dx = int(m.group(1)); break

    for pat in [r"(\d{1,4}) ?gb (?:available )?space", r"space:? (\d{1,4}) ?gb"]:
        m = re.search(pat, req)
        if m: storage_gb = int(m.group(1)); break

    stype = "ssd" if "ssd" in req else "hdd" if "hdd" in req else None
    storage = f"{stype} {storage_gb} GB" if stype and storage_gb else f"{storage_gb} GB" if storage_gb else None

    return {"ram_required_gb": ram, "directx_version": dx, "storage_requirement": storage}

def classify_hardware_requirements(text, cpu_scores, gpu_scores):
    text = text.lower()
    if not text or "no information" in text:
        return {"cpu_tier": "unknown", "gpu_tier": "unknown", "hardware_tier": "unknown", "ram_required_gb": None,
                "directx_version": None, "storage_requirement": None, "fallback_reason": "no_data"}

    cpu_score = max([cpu_scores.get(k, 0) for k in cpu_scores if k in text] + [0])
    if cpu_score == 0:
        if "dual-core" in text or "dual core" in text:
            return 2000
        if "quad-core" in text or "quad core" in text:
            return 6000
        if "hexa-core" in text or "hexa core" in text:
            return 9000
        if "octa-core" in text or "octa core" in text:
            return 12000

    gpu_score = max([gpu_scores.get(k, 0) for k in gpu_scores if k in text] + [0])

    def tier(score, bounds):
        for t, r in bounds.items():
            if score in r: return t
        return "unknown"

    tiers = {"low": range(0, 2500), "medium": range(2500, 7000), "high": range(7000, 14000), "ultra": range(14000, 999999)}
    cpu_tier = tier(cpu_score, tiers)
    gpu_tier = tier(gpu_score, {"low": range(0, 2000), "medium": range(2000, 6000), "high": range(6000, 10000), "ultra": range(10000, 999999)})

    def tier_max(t1, t2):
        order = ["low", "medium", "high", "ultra"]
        return max((t1, t2), key = lambda x: order.index(x)) if t1 in order and t2 in order else t1 or t2 or "unknown"

    return {
        "cpu_tier": cpu_tier, "gpu_tier": gpu_tier,
        "hardware_tier": tier_max(cpu_tier, gpu_tier),
        **parse_requirements(text),
        "fallback_reason": "matched_models"
    }

def process_game_data(game_data, all_tags, all_genres):
    cpu_scores = load_component_scores(CPU_BENCHMARK_PATH)
    gpu_scores = load_component_scores(GPU_BENCHMARK_PATH)

    game = game_data.copy()
    game["Features"] = generate_feature_vector(game, all_tags, all_genres)
    game["Metadata Vector"] = process_text_to_vector(create_metadata_string(game))

    game["excluded_titles"] = [game.get("Game Name", "")]
    game["release_year"] = extract_release_year(game.get("Release Date", ""))
    game["has_metacritic_score"] = has_metacritic_score(game.get("Metacritic", ""))

    game["vector_norms"] = {"metadata": compute_vector_norm(game["Metadata Vector"])}

    for key in list(game.keys()):
        if key.endswith(" Vector Norm") or key.startswith("hardware_min_") or key.startswith("hardware_rec_"):
            del game[key]

    min_req = clean_requirements_text(game.get("Minimum Requirements", ""))
    rec_req = clean_requirements_text(game.get("Recommended Requirements", ""))
    game["Minimum Requirements"] = min_req
    game["Recommended Requirements"] = rec_req
    game["hardware_analysis"] = {
        "minimum": classify_hardware_requirements(min_req, cpu_scores, gpu_scores),
        "recommended": classify_hardware_requirements(rec_req, cpu_scores, gpu_scores)
    }

    try:
        price_value = game.get("Price")
        if isinstance(price_value, str):
            price_value = price_value.replace("zł", "").replace(",", ".").strip()
        game["Price"] = float(price_value)
    except:
        game["Price"] = None

    try:
        rel_date = game.get("Release Date")
        rel_obj = datetime.strptime(rel_date, "%d %b, %Y")
        epoch = datetime(1970, 1, 1)
        game["Release Date Days"] = (rel_obj - epoch).days
    except:
        game["Release Date Days"] = None

    return game
