import requests
from bs4 import BeautifulSoup

def get_steam_tags(appid):
    url = f"https://store.steampowered.com/app/{appid}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        tags = [tag.text.strip() for tag in soup.select('.app_tag')]
        return tags
    else:
        print(f"Nie udało się uzyskać dostępu do strony Steam. Status: {response.status_code}")
        return []

appid = 374320
tags = get_steam_tags(appid)
print("Tagi:", tags)
