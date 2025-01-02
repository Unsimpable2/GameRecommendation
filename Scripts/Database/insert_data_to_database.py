import os
import json
import psycopg2
import logging
from psycopg2 import sql
from datetime import datetime

host = "localhost"
port = "1234"
dbname = "SteamGamesDB"
user = "postgres"
password = "admin"

log_dir = '../GameRecommendation/Logs/Database/'
os.makedirs(log_dir, exist_ok = True)

logging.basicConfig(
    filename=os.path.join(log_dir, 'data_import.log'),
    level = logging.INFO,
    format = '%(asctime)s - %(levelname)s - %(message)s',
    filemode = 'a'
)

def parse_release_date(release_date):
    if release_date and release_date.lower() != "coming soon":
        try:
            return datetime.strptime(release_date, "%d %b, %Y").date()
        except ValueError:
            logging.error(f"Invalid date format: {release_date}")
            return None
    else:
        logging.warning(f"Non-parsable release date: {release_date}")
        return None

def validate_integer(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def connect_to_postgres():
    try:
        connection = psycopg2.connect(
            host = host,
            port = port,
            dbname = dbname,
            user = user,
            password = password
        )

        cursor = connection.cursor()

        cursor.execute("SELECT version();")
        postgres_version = cursor.fetchone()
        logging.info(f"Connected to PostgreSQL, version: {postgres_version}")

        return connection, cursor

    except Exception as error:
        logging.error(f"Error connecting to PostgreSQL: {error}")
        return None, None

def insert_data_from_json(json_file):

    json_file = os.path.join('../GameRecommendation/Data/GamesData', json_file)

    connection, cursor = connect_to_postgres()

    if connection is None or cursor is None:
        logging.error("Failed to connect to the database. Terminating data insertion.")
        return

    if not os.path.exists(json_file):
        logging.error(f"JSON file not found: {json_file}")
        return

    try:
        with open(json_file, 'r', encoding = 'utf-8') as f:
            data = json.load(f)
        logging.info(f"Successfully loaded JSON data from file: {json_file}")
    except Exception as e:
        logging.error(f"Failed to load JSON data from file: {json_file}. Error: {e}")
        return

    success_count = 0
    error_count = 0
    batch_size = 1000

    for idx, game in enumerate(data):
        try:
            if not game.get('App ID') or not game.get('Game Name'):
                logging.error(f"Missing required fields for game: {game}")
                error_count += 1
                continue

            query = sql.SQL("""
                INSERT INTO games (
                    app_id, game_name, type, developer, publisher, is_free, price, 
                    age_rating, detailed_description, short_description, about_the_game, 
                    minimum_requirements, recommended_requirements, categories, tags, genres,
                    recommendations, release_date
                ) VALUES (
                    %(App ID)s, %(Game Name)s, %(Type)s, %(Developer)s, %(Publisher)s, %(Is Free)s, %(Price)s,
                    %(Age Rating)s, %(Detailed Description)s, %(Short Description)s, %(About the Game)s,
                    %(Minimum Requirements)s, %(Recommended Requirements)s, %(Categories)s, %(Tags)s, %(Genres)s,
                    %(Recommendations)s, %(Release Date)s
                )
                ON CONFLICT (app_id) DO NOTHING;
            """)

            cursor.execute(query, {
                'App ID': game.get('App ID'),
                'Game Name': game.get('Game Name'),
                'Type': game.get('Type'),
                'Developer': game.get('Developer'),
                'Publisher': game.get('Publisher'),
                'Is Free': game.get('Is Free'),
                'Price': game.get('Price'),
                'Age Rating': validate_integer(game.get('Age Rating')),
                'Detailed Description': game.get('Detailed Description'),
                'Short Description': game.get('Short Description'),
                'About the Game': game.get('About the Game'),
                'Minimum Requirements': game.get('Minimum Requirements'),
                'Recommended Requirements': game.get('Recommended Requirements'),
                'Categories': json.dumps(game.get('Categories')),
                'Tags': json.dumps(game.get('Tags')),
                'Genres': json.dumps(game.get('Genres')),
                'Recommendations': validate_integer(game.get('Recommendations')),
                'Release Date': parse_release_date(game.get('Release Date'))
            })

            success_count += 1

            if success_count % batch_size == 0:
                connection.commit()
                logging.info(f"Committed batch of {batch_size} records.")

        except Exception as e:
            logging.error(f"Error while inserting data for game with App ID {game.get('App ID')}. Error: {e}")
            error_count += 1
            connection.rollback()

    connection.commit()
    cursor.close()
    connection.close()

    if error_count == 0:
        logging.info(f"Successfully imported all {success_count} games from the JSON file.")
        logging.info(f"------------End of data importing------------\n")
    else:
        logging.warning(f"Import completed with {success_count} successes and {error_count} errors.")
        logging.info(f"------------End of data importing------------\n")

insert_data_from_json('steam_games_processed_part10.json')
