import requests
import json

api_key = 'TWÓJ_KLUCZ_API'
app_id = 420

url = f'https://store.steampowered.com/api/appdetails?appids={app_id}'


response = requests.get(url)
data = response.json()

if data[str(app_id)]['success']:
    gra = data[str(app_id)]['data']
    print(f"Nazwa gry: {gra['name']}")
    print(f"Gatunek: {', '.join([genre['description'] for genre in gra['genres']])}")
    print(f"Opis: {gra['short_description']}")
    print(f"Data wydania: {gra['release_date']['date']}")
else:
    print("Nie udało się pobrać danych o grze.")
