import os
import re
import sys
import json
import atexit
import logging
from psycopg2 import sql
from psycopg2.pool import PoolError
from psycopg2.extras import Json
from datetime import datetime

sys.stdout.reconfigure(encoding = 'utf-8', errors = 'replace')

from Scripts.Database.db_connection_pool import create_connection_pool, get_connection, return_connection, close_connection_pool

VECTOR_SIZE = 768
_POOL_READY = False

def setup_logger_data():
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

database_logger = setup_logger_data()

def ensure_pool(minconn = 1, maxconn = 10):
    global _POOL_READY
    if not _POOL_READY:
        create_connection_pool(minconn = minconn, maxconn = maxconn)
        _POOL_READY = True

def safe_close_pool():
    global _POOL_READY
    try:
        if _POOL_READY:
            close_connection_pool()
    except PoolError:
        pass
    _POOL_READY = False

atexit.register(safe_close_pool)

def vec_literal(vec, size=VECTOR_SIZE):
    if not isinstance(vec, list):
        vec = []
    vec = [float(x) for x in vec][:size]
    if len(vec) < size:
        vec += [0.0] * (size - len(vec))
    return "[" + ",".join(str(x) for x in vec) + "]"

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
    ensure_pool()

    query = """
        INSERT INTO games (
            app_id, game_name, type, developer, publisher, is_free, price, 
            age_rating, minimum_requirements, recommended_requirements, categories, 
            tags, genres, recommendations, release_date, release_date_days,
            features, metadata_vector, excluded_titles, release_year, has_metacritic_score,
            hardware_analysis, vector_norms
        ) VALUES (
            %(App ID)s, %(Game Name)s, %(Type)s, %(Developer)s, %(Publisher)s, %(Is Free)s, %(Price)s,
            %(Age Rating)s, %(Minimum Requirements)s, %(Recommended Requirements)s,
            %(Categories)s::jsonb, %(Tags)s::jsonb, %(Genres)s::jsonb,
            %(Recommendations)s::jsonb, %(Release Date)s, %(Release Date Days)s,
            %(Features)s::vector(768), %(Metadata Vector)s::vector(768),
            %(Excluded Titles)s, %(Release Year)s, %(Has Metacritic Score)s,
            %(Hardware Analysis)s::jsonb, %(Vector Norms)s::jsonb
        )
        ON CONFLICT (app_id) DO NOTHING
        RETURNING app_id;
    """

    def one_pass():
        connection = get_connection()
        try:
            with connection:
                with connection.cursor() as cursor:
                    success_rows = 0
                    conflict_rows = 0
                    error_rows = 0

                    if not silent:
                        database_logger.info("Started importing game data to the database...")

                    for game in data:
                        try:
                            if not game.get('App ID') or not game.get('Game Name'):
                                app_id = game.get('App ID', 'UNKNOWN')
                                msg = f"Missing required fields for game with App ID: {app_id}"
                                print(msg)
                                database_logger.error(msg)
                                error_rows += 1
                                continue

                            release_date, release_date_days = parse_release_date(game.get('Release Date'))

                            dev = game.get('Developer') or []
                            pub = game.get('Publisher') or []
                            if isinstance(dev, str): dev = [dev]
                            if isinstance(pub, str): pub = [pub]

                            excluded = game.get('excluded_titles')
                            if excluded is None:
                                excluded = []
                            elif isinstance(excluded, str):
                                try:
                                    excluded = json.loads(excluded)
                                except Exception:
                                    excluded = [excluded]
                            elif not isinstance(excluded, (list, tuple)):
                                excluded = [str(excluded)]
                            excluded = [str(x) for x in excluded]

                            params = {
                                'App ID': game.get('App ID'),
                                'Game Name': game.get('Game Name'),
                                'Type': game.get('Type'),
                                'Developer': dev,
                                'Publisher': pub,
                                'Is Free': game.get('Is Free'),
                                'Price': game.get('Price'),
                                'Age Rating': validate_integer(game.get('Age Rating')),
                                'Minimum Requirements': game.get('Minimum Requirements'),
                                'Recommended Requirements': game.get('Recommended Requirements'),
                                'Categories': json.dumps(game.get('Categories')),
                                'Tags': json.dumps(game.get('Tags')),
                                'Genres': json.dumps(game.get('Genres')),
                                'Recommendations': json.dumps(game.get('Recommendations')),
                                'Release Date': release_date,
                                'Release Date Days': release_date_days,
                                'Features': vec_literal(game.get('Features', [])),
                                'Metadata Vector': vec_literal(game.get('Metadata Vector', [])),
                                'Excluded Titles': excluded,
                                'Release Year': game.get('release_year'),
                                'Has Metacritic Score': game.get('has_metacritic_score'),
                                'Hardware Analysis': json.dumps(game.get('hardware_analysis')),
                                'Vector Norms': json.dumps(game.get('vector_norms')),
                            }

                            cursor.execute(query, params)
                            ret = cursor.fetchone()
                            if ret:
                                success_rows += 1
                            else:
                                conflict_rows += 1

                        except Exception as e:
                            error_rows += 1
                            print(f"[INSERT ERROR app_id={game.get('App ID')}] {e}")
                            database_logger.error(f"Error inserting data for game {game.get('App ID')}: {e}")
                            connection.rollback()

                    if not silent:
                        if error_rows == 0:
                            database_logger.info(f"Inserted: {success_rows}, conflicts (skipped): {conflict_rows}.")
                        else:
                            database_logger.warning(
                                f"Inserted: {success_rows}, conflicts: {conflict_rows}, errors: {error_rows}."
                            )
                        database_logger.info("------------End of data importing------------\n")
        finally:
            return_connection(connection)

    try:
        one_pass()
    except PoolError:
        database_logger.warning("PoolError: pool was closed. Recreating pool and retrying once...")
        safe_close_pool()
        ensure_pool()
        one_pass()
    except Exception as e:
        print(f"[CRITICAL INSERT ERROR] {e}")
        database_logger.error(f"Critical error: {e}")
