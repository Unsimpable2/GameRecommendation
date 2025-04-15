import os
import re
import sys
import json
import logging
from psycopg2 import sql
from datetime import datetime

sys.stdout.reconfigure(encoding = 'utf-8', errors = 'replace')

from Scripts.Database.db_connection_pool import get_connection, return_connection

VECTOR_SIZE = 768

def setup_logger():
    log_dir = '../GameRecommendation/Logs/Database'
    os.makedirs(log_dir, exist_ok = True)
    log_file_path = os.path.join(log_dir, 'data_import.log')
    logger = logging.getLogger(__name__)
    handler = logging.FileHandler(log_file_path, mode = 'w')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

database_logger = setup_logger()

def log_start_of_insert_session():
    database_logger.info("Started inserting games in streaming mode (one by one)...")

def log_end_of_insert_session(total_successes):
    database_logger.info(f"Finished inserting games in streaming mode. Total games inserted: {total_successes[0]}")
    database_logger.info("------------End of stream insert session------------\n")

def parse_release_date(release_date):
    if not release_date:
        return None, None

    clean_value = str(release_date).strip().lower()
    invalid_values = {"coming soon", "to be announced", "tba", "soon", "unavailable", "n/a", "not available"}

    if clean_value in invalid_values:
        return None, None

    epoch = datetime(1970, 1, 1)

    date_formats = [
        "%d %b, %Y",    
        "%b %d, %Y",    
        "%B %Y",        
        "%b %Y",        
        "%Y",          
    ]

    for fmt in date_formats:
        try:
            release_date_obj = datetime.strptime(release_date, fmt)
            release_date_days = (release_date_obj - epoch).days
            return release_date_obj.date(), release_date_days
        except ValueError:
            continue

    q_match = re.match(r"Q([1-4])\s+(\d{4})", release_date, re.IGNORECASE)
    if q_match:
        quarter = int(q_match.group(1))
        year = int(q_match.group(2))
        approx_month = {1: 2, 2: 5, 3: 8, 4: 11}[quarter]
        try:
            release_date_obj = datetime(year, approx_month, 15)
            release_date_days = (release_date_obj - epoch).days
            return release_date_obj.date(), release_date_days
        except Exception:
            pass

    database_logger.warning(f"Invalid or unhandled date format: {release_date}")
    return None, None

def validate_integer(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None

def normalize_vector(vector, size = VECTOR_SIZE):
    if not isinstance(vector, list):
        return [0.0] * size
    vector = [float(x) for x in vector]
    if len(vector) > size:
        return vector[:size]
    return vector + [0.0] * (size - len(vector))

def insert_data_from_object(data, silent = False):
    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        success_count = 0
        error_count = 0
        batch_size = 1000

        if not silent:
            database_logger.info("Started importing game data to the database...")

        for game in data:
            try:
                if not game.get('App ID') or not game.get('Game Name'):
                    app_id = game.get('App ID', 'UNKNOWN')
                    database_logger.error(f"Missing required fields for game with App ID: {app_id}")
                    error_count += 1
                    continue

                query = """
                    INSERT INTO games (
                        app_id, game_name, type, developer, publisher, is_free, price, 
                        age_rating, detailed_description, short_description, about_the_game, 
                        minimum_requirements, recommended_requirements, categories, tags, genres,
                        recommendations, release_date, release_date_days,
                        features, detailed_description_vector, about_the_game_vector, short_description_vector,
                        metadata_vector
                    ) VALUES (
                        %(App ID)s, %(Game Name)s, %(Type)s, %(Developer)s, %(Publisher)s, %(Is Free)s, %(Price)s,
                        %(Age Rating)s, %(Detailed Description)s, %(Short Description)s, %(About the Game)s,
                        %(Minimum Requirements)s, %(Recommended Requirements)s, %(Categories)s, %(Tags)s, %(Genres)s,
                        %(Recommendations)s, %(Release Date)s, %(Release Date Days)s,
                        %(Features)s, %(Detailed Description Vector)s, %(About the Game Vector)s, %(Short Description Vector)s,
                        %(Metadata Vector)s
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
                    'Features': normalize_vector(game.get('Features', []), VECTOR_SIZE),
                    'Detailed Description Vector': normalize_vector(game.get('Detailed Description Vector', []), VECTOR_SIZE),
                    'About the Game Vector': normalize_vector(game.get('About the Game Vector', []), VECTOR_SIZE),
                    'Short Description Vector': normalize_vector(game.get('Short Description Vector', []), VECTOR_SIZE),
                    'Metadata Vector': normalize_vector(game.get('Metadata Vector', []), VECTOR_SIZE)
                })

                success_count += 1

                if success_count % batch_size == 0:
                    connection.commit()
                    database_logger.info(f"Committed batch of {batch_size} records.")

            except Exception as e:
                error_count += 1
                database_logger.error(f"Error inserting data for game {game.get('App ID')}: {e}")
                connection.rollback()

        connection.commit()

        if not silent:
            if error_count == 0:
                database_logger.info(f"Successfully imported all {success_count} games.")
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
