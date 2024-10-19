import requests
import json

app_id = 570

# Endpoint API do pobrania statystyk gry
url = f'http://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={app_id}'

# Wysyłanie żądania
response = requests.get(url)
data = response.json()

# Wyświetlanie liczby aktywnych graczy
if 'response' in data and 'player_count' in data['response']:
    print(f"Liczba aktualnych graczy: {data['response']['player_count']}")
else:
    print("Nie udało się pobrać danych.")

