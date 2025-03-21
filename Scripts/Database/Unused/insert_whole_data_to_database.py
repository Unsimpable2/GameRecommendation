import os
import json
import logging
from psycopg import sql
from datetime import datetime
from db_connection_pool import create_connection_pool, get_connection, return_connection

VECTOR_SIZE = 384

def setup_logger():
    log_dir = '../GameRecommendation/Logs/Database'
    os.makedirs(log_dir, exist_ok = True)
    log_file_path = os.path.join(log_dir, 'data_import.log')

    logger = logging.getLogger(__name__)
    handler = logging.FileHandler(log_file_path, mode = 'w', encoding = 'utf-8')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

database_logger = setup_logger()

def parse_release_date(release_date):
    if not release_date:
        return None, None

    clean_value = str(release_date).strip().lower()
    invalid_values = ["coming soon", "to be announced", "tba", "soon", "unavailable"]

    if clean_value in invalid_values:
        database_logger.warning(f"Non-parsable release date: {release_date}")
        return None, None

    try:
        release_date_obj = datetime.strptime(release_date, "%d %b, %Y")
        epoch = datetime(1970, 1, 1)
        release_date_days = (release_date_obj - epoch).days
        return release_date_obj.date(), release_date_days
    except ValueError:
        pass

    try:
        if len(release_date) == 4 and release_date.isdigit():
            year_obj = datetime.strptime(release_date, "%Y")
            return year_obj.date(), None
    except Exception:
        pass

    database_logger.error(f"Invalid date format: {release_date}")
    return None, None

def validate_integer(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None

def ensure_vector_size(vector, size = VECTOR_SIZE):
    if not isinstance(vector, list):
        return [0.0] * size
    if len(vector) > size:
        return vector[:size]
    return vector + [0.0] * (size - len(vector))

def insert_data_from_json(json_file):
    create_connection_pool(minconn = 1, maxconn = 10)
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

                query = """
                    INSERT INTO games (
                        app_id, game_name, type, developer, publisher, is_free, price, 
                        age_rating, detailed_description, short_description, about_the_game, 
                        minimum_requirements, recommended_requirements, categories, tags, genres,
                        recommendations, release_date, release_date_days,
                        features, detailed_description_vector, about_the_game_vector, short_description_vector
                    ) VALUES (
                        %(App ID)s, %(Game Name)s, %(Type)s, %(Developer)s, %(Publisher)s, %(Is Free)s, %(Price)s,
                        %(Age Rating)s, %(Detailed Description)s, %(Short Description)s, %(About the Game)s,
                        %(Minimum Requirements)s, %(Recommended Requirements)s, %(Categories)s, %(Tags)s, %(Genres)s,
                        %(Recommendations)s, %(Release Date)s, %(Release Date Days)s,
                        %(Features)s, %(Detailed Description Vector)s, %(About the Game Vector)s, %(Short Description Vector)s
                    )
                    ON CONFLICT (app_id) DO NOTHING;
                """

                release_date, release_date_days = parse_release_date(game.get('Release Date'))

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
                    'Release Date': release_date,
                    'Release Date Days': release_date_days,
                    'Features': ensure_vector_size(game.get('Features', []), VECTOR_SIZE),
                    'Detailed Description Vector': ensure_vector_size(game.get('Detailed Description Vector', []), VECTOR_SIZE),
                    'About the Game Vector': ensure_vector_size(game.get('About the Game Vector', []), VECTOR_SIZE),
                    'Short Description Vector': ensure_vector_size(game.get('Short Description Vector', []), VECTOR_SIZE)
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

for n in range(1, 24):
    insert_data_from_json(f'steam_games_processed_vector_part{n}.json')
