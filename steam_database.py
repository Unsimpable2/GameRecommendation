import json
import requests

url = 'http://api.steampowered.com/ISteamApps/GetAppList/v2/'

response = requests.get(url)
data = response.json()

# Zapisz całą listę gier do pliku JSON
with open('lista_gier_steam.json', 'w', encoding='utf-8') as file:
    json.dump(data['applist']['apps'], file, ensure_ascii=False, indent=4)

print("Lista gier została zapisana do pliku lista_gier_steam.json")
