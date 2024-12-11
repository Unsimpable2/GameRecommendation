import json

def make_hashable(item):
    if isinstance(item, dict):
        return tuple((key, make_hashable(value)) for key, value in item.items())
    elif isinstance(item, list):
        return tuple(make_hashable(elem) for elem in item)
    return item

def delete_duplicates(nr):
    file_path = f'../GameRecommendation/Data/GamesData/steam_games_processed_part{nr}.json'
    with open(file_path, 'r', encoding = 'utf-8') as f:
        data = json.load(f)

    unique_data = []
    seen_sections = set()

    for entry in data:
        entry_tuple = make_hashable(entry)
        
        if entry_tuple not in seen_sections:
            seen_sections.add(entry_tuple)
            unique_data.append(entry)

    with open(file_path, 'w', encoding = 'utf-8') as f:
        json.dump(unique_data, f, indent = 4, ensure_ascii = False)

    print("Duplicates have been removed.")

delete_duplicates(10)
