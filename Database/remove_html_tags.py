import json
import re
import os

def remove_html_tags(text):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

def clean_json_data(json_data):
    if isinstance(json_data, dict):
        return {key: clean_json_data(value) for key, value in json_data.items()}
    elif isinstance(json_data, list):
        return [clean_json_data(item) for item in json_data]
    elif isinstance(json_data, str):
        return remove_html_tags(json_data)
    else:
        return json_data

def clean_and_overwrite_json(file_path):
    with open(file_path, 'r', encoding = 'utf-8') as file:
        data = json.load(file)

    cleaned_data = clean_json_data(data)

    with open(file_path, 'w', encoding = 'utf-8') as file:
        json.dump(cleaned_data, file, ensure_ascii = False, indent=4)

    print(f'Data has been cleaned and overwritten in the file {file_path}')

file_path = os.path.join('../MasterDeg/Database/SteamDatabase', 'steam_games_processed_part3.json')

clean_and_overwrite_json(file_path)
