import json
import requests
import os

def get_steam_database():
    url = 'http://api.steampowered.com/ISteamApps/GetAppList/v2/'

    response = requests.get(url)
    data = response.json()
    new_database_path = os.path.join('../MasterDeg/Database/SteamDatabase', 'steam_game_list_new.json')
    with open(new_database_path, 'w', encoding = 'utf-8') as file:
        json.dump(data['applist']['apps'], file, ensure_ascii = False, indent = 4)

    print("The game list has been saved to the steam_game_list_new.json file")

get_steam_database()