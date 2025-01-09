import os
import json
import logging
from psycopg2 import sql
from datetime import datetime


from db_connection_pool import get_connection, return_connection

def setup_logger():
    log_dir = '../GameRecommendation/Logs/Database'
    os.makedirs(log_dir, exist_ok = True)

    log_file_path = os.path.join(log_dir, 'data_import.log')

    logger = logging.getLogger(__name__)
    handler = logging.FileHandler(log_file_path, mode = 'a')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

database_logger = setup_logger()

def parse_release_date(release_date):
    if not release_date or release_date.lower() == "coming soon":
        database_logger.warning(f"Non-parsable release date: {release_date}")
        current_year = datetime.now().year
        return datetime(current_year + 1, 1, 1).date()
    try:
        return datetime.strptime(release_date, "%d %b, %Y").date()
    except ValueError:
        try:
            return datetime.strptime(release_date, "%Y").date()
        except ValueError:
            database_logger.error(f"Invalid date format: {release_date}")
            return datetime.now().date()

def validate_integer(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def insert_data_from_json(json_file):
    json_file = os.path.join('../GameRecommendation/Data/GamesData', json_file)

    connection = None
    try:
        connection = get_connection()
        cursor = connection.cursor()

        if not os.path.exists(json_file):
            database_logger.error(f"JSON file not found: {json_file}")
            return

        try:
            with open(json_file, 'r', encoding = 'utf-8') as f:
                data = json.load(f)
            database_logger.info(f"Successfully loaded JSON data from file: {json_file}")
        except Exception as e:
            database_logger.error(f"Failed to load JSON data from file: {json_file}. Error: {e}")
            return

        success_count = 0
        error_count = 0
        batch_size = 1000

        for idx, game in enumerate(data):
            try:
                if not game.get('App ID') or not game.get('Game Name'):
                    database_logger.error(f"Missing required fields for game: {game}")
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
                    database_logger.info(f"Committed batch of {batch_size} records.")

            except Exception as e:
                error_count += 1
                database_logger.error(f"Error while inserting data for game with App ID {game.get('App ID')}. Error: {e}")
                connection.rollback()

        connection.commit()

        if error_count == 0:
            database_logger.info(f"Successfully imported all {success_count} games from the JSON file.")
            database_logger.info(f"------------End of data importing------------\n")
        else:
            database_logger.warning(f"Import completed with {success_count} successes and {error_count} errors.")
            database_logger.info(f"------------End of data importing------------\n")

    except Exception as e:
        database_logger.error(f"Critical error: {e}")
        if connection:
            connection.rollback()
    finally:
        if connection:
            return_connection(connection)

insert_data_from_json('steam_games_processed_part10.json')
