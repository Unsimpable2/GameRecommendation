import json
import requests
import html
from bs4 import BeautifulSoup
import time
import logging

logging.basicConfig(filename='steam_games.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_game_details(app_id, retries=3):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=english"
    for attempt in range(retries):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if str(app_id) in data and data[str(app_id)]['success']:
                    if data[str(app_id)]['data']['type'] == 'game':
                        return data[str(app_id)]['data']
            else:
                logging.warning(f"Invalid response status for ID {app_id}: {response.status_code}")
        except requests.RequestException as e:
            logging.error(f"Error fetching data for ID {app_id}: {str(e)}")
        
        time.sleep(1)
    return None

def remove_html_tags(text):
    if not text or text.strip() == "":
        return ""
    soup = BeautifulSoup(text, "html.parser")
    clean_text = soup.get_text(separator=" ")
    return clean_text.replace("\n", " ")

def save_games_data(app_id=None):
    url = 'http://api.steampowered.com/ISteamApps/GetAppList/v2/'
    try:
        response = requests.get(url)
        data = response.json()
    except requests.RequestException as e:
        logging.error(f"Error fetching game list: {str(e)}")
        return

    games = []

    if app_id: 
        game_details = get_game_details(app_id)
        if game_details:
            games.append(process_game_details(app_id, game_details))
    else:  
        for app in data['applist']['apps']:
            app_id = app['appid']
            game_details = get_game_details(app_id)
            if game_details:
                games.append(process_game_details(app_id, game_details))
            else:
                logging.info(f"Skipped game with ID: {app_id}")

    with open('test.json', 'w', encoding='utf-8') as file:
        json.dump(games, file, ensure_ascii=False, indent=4)

    print(f"Data for {'all games' if not app_id else f'game with ID {app_id}'} has been saved to steam_game_list.json")

def process_game_details(app_id, game_details):
    try:
        is_free = game_details.get('is_free', False)

        if is_free:
            price = "Free"
        else:
            price = game_details.get('price_overview', {}).get('final_formatted', 'N/A')

        detailed_description = game_details.get('detailed_description', '')
        detailed_description = html.unescape(detailed_description)
        detailed_description = remove_html_tags(detailed_description).replace("\n", " ")

        short_description = game_details.get('detailed_description', 'No data')
        short_description = html.unescape(short_description)
        short_description = remove_html_tags(short_description).replace("\n", " ")

        about_game = game_details.get('detailed_description', 'No data')
        about_game = html.unescape(about_game)
        about_game = remove_html_tags(about_game).replace("\n", " ")

        pc_requirements = game_details.get('pc_requirements', {})
        
        if isinstance(pc_requirements, dict):
            minimal_requirements = pc_requirements.get('minimum', 'No data')
            recommended_requirements = pc_requirements.get('recommended', 'None')
        else:
            minimal_requirements = 'No data'
            recommended_requirements = 'No data'

        minimal_requirements = remove_html_tags(minimal_requirements).replace("\n", " ")
        recommended_requirements = remove_html_tags(recommended_requirements).replace("\n", " ") if recommended_requirements != 'None' else 'No data'

        return {
            'App ID': app_id,
            'Game Name': game_details['name'],
            'Type': game_details['type'],
            'Developer': game_details.get('developers', []),
            'Publisher': game_details.get('publishers', []),
            'Is Free': is_free,
            'Price': price,
            'Age Rating': game_details.get('required_age', 'N/A'),
            'Detailed Description': detailed_description,
            'Short Description': short_description,
            'About the Game': about_game,
            'Minimum Requirements': minimal_requirements,
            'Recommended Requirements': recommended_requirements,
            'Categories': game_details.get('categories', [])
        }
    except Exception as e:
        logging.error(f"Error processing data for game with ID {app_id}: {str(e)}")
        return None

#save_games_data()
save_games_data(app_id=570)