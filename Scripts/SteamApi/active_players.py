import json
import os
import requests

def get_app_id_by_name(game_name):
    file_path = os.path.join('../GameRecommendation/Data/IDList/BaseList', 'steam_game_list_base.json')

    if not os.path.exists(file_path):
        print(f"Error: The file '{file_path}' does not exist.")
        return None

    with open(file_path, 'r', encoding = 'utf-8') as file:
        games_data = json.load(file)

        for game in games_data:
            if game_name.lower() == game['name'].lower():
                return game['appid']

    print(f"Game '{game_name}' not found in the database.")
    return None

def active_players(game_name):
    app_id = get_app_id_by_name(game_name)

    if app_id:
        player_count_url = f'http://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={app_id}'
        
        player_count_response = requests.get(player_count_url)
        player_count_data = player_count_response.json()

        if 'response' in player_count_data and 'player_count' in player_count_data['response']:
            player_count = player_count_data['response']['player_count']
            print(f"Current number of players in {game_name}: {player_count}")
        else:
            print("Failed to retrieve player count.")
    else:
        print(f"Game '{game_name}' not found in the database.")


active_players("The Witcher 3 REDkit")
