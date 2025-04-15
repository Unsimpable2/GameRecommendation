import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-base-en-v1.5")

VECTOR_SIZE = 768

def round_vector(vector, precision = 4, target_length = VECTOR_SIZE):
    rounded = [round(x, precision) for x in vector]
    if len(rounded) > target_length:
        return rounded[:target_length]
    elif len(rounded) < target_length:
        return rounded + [0.0] * (target_length - len(rounded))
    return rounded

def generate_feature_vector(game_data, all_tags, all_genres):
    tag_vector = np.zeros(len(all_tags))
    for tag in game_data.get("Tags", []):
        if tag in all_tags:
            tag_vector[all_tags.index(tag)] = 1

    genre_vector = np.zeros(len(all_genres))
    for genre in game_data.get("Genres", []):
        genre_description = genre.get("description", "")
        if genre_description in all_genres:
            genre_vector[all_genres.index(genre_description)] = 1

    recommendations = game_data.get("Recommendations", 0)
    try:
        recommendations_normalized = int(recommendations) / 100000
    except (ValueError, TypeError):
        recommendations_normalized = 0

    feature_vector = np.concatenate([tag_vector, genre_vector, [recommendations_normalized]])
    return round_vector(feature_vector, precision = 4, target_length = VECTOR_SIZE)

def process_release_date(date_str):
    if not date_str:
        return date_str, None

    try:
        release_date_obj = datetime.strptime(date_str, "%d %b, %Y")
        epoch = datetime(1970, 1, 1)
        release_date_days = (release_date_obj - epoch).days
        return date_str, release_date_days
    except ValueError:
        pass

    if len(date_str) == 4 and date_str.isdigit():
        return date_str, None

    return date_str, None

def process_text_to_vector(text):
    vector = model.encode(text).tolist()
    return round_vector(vector, precision = 4, target_length = VECTOR_SIZE)

def create_metadata_string(game_data):
    tags = ", ".join(game_data.get("Tags", []))
    genres = ", ".join([g.get("description", "") for g in game_data.get("Genres", [])])
    categories = ", ".join([c.get("description", "") for c in game_data.get("Categories", [])])
    return f"Tags: {tags}. Genres: {genres}. Categories: {categories}."

def game_data_to_vector(game_data, all_tags, all_genres):
    processed_game = game_data.copy()

    processed_game["Features"] = generate_feature_vector(game_data, all_tags, all_genres)
    processed_game["Detailed Description Vector"] = process_text_to_vector(game_data.get("Detailed Description", ""))
    processed_game["About the Game Vector"] = process_text_to_vector(game_data.get("About the Game", ""))
    processed_game["Short Description Vector"] = process_text_to_vector(game_data.get("Short Description", ""))

    metadata_text = create_metadata_string(game_data)
    processed_game["Metadata Vector"] = process_text_to_vector(metadata_text)

    try:
        price_value = game_data.get("Price")
        if isinstance(price_value, str):
            price_value = price_value.replace("zł", "").replace(",", ".").strip()
        processed_game["Price"] = float(price_value)
    except (ValueError, TypeError, AttributeError):
        processed_game["Price"] = None

    release_date, release_date_days = process_release_date(game_data.get("Release Date", None))
    processed_game["Release Date"] = release_date
    processed_game["Release Date Days"] = release_date_days

    return processed_game