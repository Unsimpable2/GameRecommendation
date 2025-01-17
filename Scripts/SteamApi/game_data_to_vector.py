import os
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from datetime import datetime


os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

model = SentenceTransformer('all-MiniLM-L6-v2')

def round_vector(vector, precision=4):
    return [round(x, precision) for x in vector]

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
    return feature_vector.tolist()

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
    return round_vector(model.encode(text).tolist(), precision=4)

def process_json_file(input_file_path, output_file_path):
    with open(input_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    all_tags = list({tag for game in data for tag in game.get("Tags", [])})
    all_genres = list({genre["description"] for game in data for genre in game.get("Genres", [])})

    processed_data = []
    for game in data:
        feature_vector = generate_feature_vector(game, all_tags, all_genres)

        detailed_description_vector = process_text_to_vector(game.get("Detailed Description", ""))
        about_game_vector = process_text_to_vector(game.get("About the Game", ""))
        short_description_vector = process_text_to_vector(game.get("Short Description", ""))

        price_str = game.get("Price", "").replace("zł", "").replace(",", ".").strip()
        try:
            game["Price"] = float(price_str)
        except ValueError:
            game["Price"] = None

        release_date, release_date_days = process_release_date(game.get("Release Date", None))
        game["Release Date"] = release_date
        game["Release Date Days"] = release_date_days

        game["Features"] = round_vector(feature_vector, precision=4)
        game["Detailed Description Vector"] = detailed_description_vector
        game["About the Game Vector"] = about_game_vector
        game["Short Description Vector"] = short_description_vector

        processed_data.append(game)

    with open(output_file_path, 'w', encoding='utf-8') as file:
        json.dump(processed_data, file, ensure_ascii=False, separators=(',', ':'))

input_file_path = "../GameRecommendation/Data/GamesData/steam_games_processed_part2.json"
output_file_path = "../GameRecommendation/Data/GamesData/steam_games_processed_part2_data_change.json"

process_json_file(input_file_path, output_file_path)
