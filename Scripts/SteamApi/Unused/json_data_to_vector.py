import os
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from datetime import datetime

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

model = SentenceTransformer('BAAI/bge-base-en-v1.5')

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

def generate_metadata_vector(game_data):
    tags = game_data.get("Tags", [])
    genres = [g.get("description", "") for g in game_data.get("Genres", [])]
    categories = [c.get("description", "") for c in game_data.get("Categories", [])]
    combined_text = " ".join(tags + genres + categories)
    return round_vector(model.encode(combined_text).tolist(), precision = 4, target_length = VECTOR_SIZE)

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

    try:
        if len(date_str) == 4 and date_str.isdigit():
            return date_str, None
    except ValueError:
        pass

    return date_str, None

def process_text_to_vector(text):
    vector = model.encode(text).tolist()
    return round_vector(vector, precision = 4, target_length = VECTOR_SIZE)

def process_json_file(input_file_path, output_file_path):
    with open(input_file_path, 'r', encoding = 'utf-8') as file:
        data = json.load(file)

    all_tags = list({tag for game in data for tag in game.get("Tags", [])})
    all_genres = list({genre["description"] for game in data for genre in game.get("Genres", [])})

    processed_data = []

    for game in data:
        feature_vector = generate_feature_vector(game, all_tags, all_genres)

        detailed_description_vector = process_text_to_vector(game.get("Detailed Description", ""))
        about_game_vector = process_text_to_vector(game.get("About the Game", ""))
        short_description_vector = process_text_to_vector(game.get("Short Description", ""))
        metadata_vector = generate_metadata_vector(game)

        try:
            price_value = game.get("Price")
            if isinstance(price_value, str):
                price_value = price_value.replace("zł", "").replace(",", ".").strip()
            game["Price"] = float(price_value)
        except (ValueError, TypeError, AttributeError):
            game["Price"] = None

        release_date, release_date_days = process_release_date(game.get("Release Date", None))
        game["Release Date"] = release_date
        game["Release Date Days"] = release_date_days

        game["Features"] = feature_vector
        game["Detailed Description Vector"] = detailed_description_vector
        game["About the Game Vector"] = about_game_vector
        game["Short Description Vector"] = short_description_vector
        game["Metadata Vector"] = metadata_vector

        processed_data.append(game)

    with open(output_file_path, 'w', encoding = 'utf-8') as file:
        json.dump(processed_data, file, ensure_ascii = False, separators = (',', ':'))

for n in range(19, 24):
    input_file_path = f"../GameRecommendation/Data/GamesData/steam_games_processed_part{n}.json"
    output_file_path = f"../GameRecommendation/Data/GamesData/steam_games_processed_vector_part{n}.json"
    process_json_file(input_file_path, output_file_path)
