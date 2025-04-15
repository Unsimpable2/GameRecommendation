import json
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

DetectorFactory.seed = 0

def filter_non_cjk_entries(nr):
    file_path = f"../GameRecommendation/Data/GamesData/steam_games_processed_part{nr}.json"

    with open(file_path, 'r', encoding = 'utf-8') as f:
        data = json.load(f)
    
    fields_to_check = ["Game Name", "Detailed Description", "Short Description", "About the Game"]
    cjk_languages = ['zh-cn', 'zh-tw', 'ja', 'ko']

    filtered_data = []
    
    for entry in data:
        contains_cjk = False
        for field in fields_to_check:
            if field in entry and entry[field]:
                try:
                    detected_language = detect(entry[field])
                    if detected_language in cjk_languages:
                        contains_cjk = True
                        break
                except LangDetectException:
                    pass

        if not contains_cjk:
            filtered_data.append(entry)
    
    with open(file_path, 'w', encoding = 'utf-8') as f:
        json.dump(filtered_data, f, ensure_ascii = False, indent = 4)

filter_non_cjk_entries(10)
