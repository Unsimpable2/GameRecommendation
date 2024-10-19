import json
import requests

url = 'http://api.steampowered.com/ISteamApps/GetAppList/v2/'

response = requests.get(url)
data = response.json()

with open('steam_game_list.json', 'w', encoding='utf-8') as file:
    json.dump(data['applist']['apps'], file, ensure_ascii=False, indent=4)

print("The game list has been saved to the steam_game_list.json file")