#import os
#import re
#import sys
#import json
#import gzip
#import logging
#from psycopg2 import sql
#from datetime import datetime
#
#sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
#
#from Scripts.Database.db_connection_pool import create_connection_pool, get_connection, return_connection
#
#VECTOR_SIZE = 768
#
#def setup_logger_whole():
#    log_dir = '../GameRecommendation/Logs/Database'
#    os.makedirs(log_dir, exist_ok = True)
#    log_file_path = os.path.join(log_dir, 'data_import2.log')
#
#    logger = logging.getLogger(__name__)
#    handler = logging.FileHandler(log_file_path, mode = 'w', encoding = 'utf-8')
#    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
#    handler.setFormatter(formatter)
#    logger.addHandler(handler)
#    logger.setLevel(logging.INFO)
#    return logger
#
#database_logger = setup_logger_whole()
#
#def parse_release_date_whole(release_date):
#    if not release_date:
#        return None, None
#
#    clean_value = str(release_date).strip().lower()
#    invalid_values = {"coming soon", "to be announced", "tba", "soon", "unavailable", "n/a", "not available"}
#
#    if clean_value in invalid_values:
#        return None, None
#
#    epoch = datetime(1970, 1, 1)
#
#    date_formats = [
#        "%d %b, %Y",    
#        "%b %d, %Y",    
#        "%B %Y",        
#        "%b %Y",        
#        "%Y",          
#    ]
#
#    for fmt in date_formats:
#        try:
#            release_date_obj = datetime.strptime(release_date, fmt)
#            release_date_days = (release_date_obj - epoch).days
#            return release_date_obj.date(), release_date_days
#        except ValueError:
#            continue
#
#    q_match = re.match(r"Q([1-4])\s+(\d{4})", release_date, re.IGNORECASE)
#    if q_match:
#        quarter = int(q_match.group(1))
#        year = int(q_match.group(2))
#        approx_month = {1: 2, 2: 5, 3: 8, 4: 11}[quarter]
#        try:
#            release_date_obj = datetime(year, approx_month, 15)
#            release_date_days = (release_date_obj - epoch).days
#            return release_date_obj.date(), release_date_days
#        except Exception:
#            pass
#
#    database_logger.warning(f"Invalid or unhandled date format: {release_date}")
#    return None, None
#
#def validate_integer(value):
#    if isinstance(value, int):
#        return value
#    if isinstance(value, str) and value.strip().isdigit():
#        return int(value.strip())
#    return None
#
#def normalize_vector_whole(vector, size = VECTOR_SIZE):
#    if not isinstance(vector, list):
#        return [0.0] * size
#    vector = [float(x) for x in vector]
#    if len(vector) > size:
#        return vector[:size]
#    return vector + [0.0] * (size - len(vector))
#
#def load_json_file_whole(base_filename):
#    base_path = os.path.join('../GameRecommendation/Data/GamesData', base_filename)
#
#    for ext in [".jsonl", ".jsonl.gz", ".gz", ".json"]:
#        full_path = base_path + ext
#        if os.path.exists(full_path):
#            if ext.endswith(".gz"):
#                open_func = gzip.open
#            else:
#                open_func = open
#
#            try:
#                if "jsonl" in ext:
#                    with open_func(full_path, "rt", encoding="utf-8") as f:
#                        return [json.loads(line) for line in f if line.strip()], full_path
#                else:
#                    with open_func(full_path, "rt", encoding="utf-8") as f:
#                        return json.load(f), full_path
#            except Exception as e:
#                raise ValueError(f"Error while reading file {full_path}: {e}")
#
#    raise FileNotFoundError(f"No JSONL.GZ file found for base: {base_filename}")
#
#def insert_data_from_json_file(base_filename):
#    create_connection_pool(minconn = 1, maxconn = 10)
#
#    connection = None
#
#    try:
#        connection = get_connection()
#        cursor = connection.cursor()
#
#        try:
#            data, file_used = load_json_file_whole(base_filename)
#            database_logger.info(f"Successfully loaded JSONL.GZ data from file: {file_used}")
#        except Exception as e:
#            database_logger.error(f"Failed to load JSONL.GZ data for base: {base_filename}. Error: {e}")
#            return
#
#        success_count = 0
#        error_count = 0
#        missing_dates_count = 0
#        batch_size = 1000
#
#        for idx, game in enumerate(data):
#            try:
#                if not game.get('App ID') or not game.get('Game Name'):
#                    app_id = game.get('App ID', 'UNKNOWN')
#                    database_logger.error(f"Missing required fields for game with App ID: {app_id}")
#                    error_count += 1
#                    continue
#
#                release_date, release_date_days = parse_release_date_whole(game.get('Release Date'))
#                
#                inserted = cursor.rowcount > 0
#                if inserted and release_date is None:
#                    missing_dates_count += 1
#
#                query = """
#                    INSERT INTO games (
#                        app_id, game_name, type, developer, publisher, is_free, price, 
#                        age_rating, detailed_description, short_description, about_the_game, 
#                        minimum_requirements, recommended_requirements, categories, tags, genres,
#                        recommendations, release_date, release_date_days,
#                        features, detailed_description_vector, about_the_game_vector, short_description_vector,
#                        metadata_vector, excluded_titles, release_year, has_metacritic_score,
#                        hardware_analysis, vector_norms
#                    ) VALUES (
#                        %(App ID)s, %(Game Name)s, %(Type)s, %(Developer)s, %(Publisher)s, %(Is Free)s, %(Price)s,
#                        %(Age Rating)s, %(Detailed Description)s, %(Short Description)s, %(About the Game)s,
#                        %(Minimum Requirements)s, %(Recommended Requirements)s, %(Categories)s, %(Tags)s, %(Genres)s,
#                        %(Recommendations)s, %(Release Date)s, %(Release Date Days)s,
#                        %(Features)s, %(Detailed Description Vector)s, %(About the Game Vector)s, %(Short Description Vector)s,
#                        %(Metadata Vector)s, %(Excluded Titles)s, %(Release Year)s, %(Has Metacritic Score)s,
#                        %(Hardware Analysis)s, %(Vector Norms)s
#                    )
#                    ON CONFLICT (app_id) DO NOTHING;
#                """
#
#                cursor.execute(query, {
#                    'App ID': game.get('App ID'),
#                    'Game Name': game.get('Game Name'),
#                    'Type': game.get('Type'),
#                    'Developer': game.get('Developer'),
#                    'Publisher': game.get('Publisher'),
#                    'Is Free': game.get('Is Free'),
#                    'Price': game.get('Price'),
#                    'Age Rating': validate_integer(game.get('Age Rating')),
#                    'Detailed Description': game.get('Detailed Description'),
#                    'Short Description': game.get('Short Description'),
#                    'About the Game': game.get('About the Game'),
#                    'Minimum Requirements': game.get('Minimum Requirements'),
#                    'Recommended Requirements': game.get('Recommended Requirements'),
#                    'Categories': json.dumps(game.get('Categories')),
#                    'Tags': json.dumps(game.get('Tags')),
#                    'Genres': json.dumps(game.get('Genres')),
#                    'Recommendations': json.dumps(game.get('Recommendations')),
#                    'Release Date': release_date,
#                    'Release Date Days': release_date_days,
#                    'Features': normalize_vector_whole(game.get('Features', []), VECTOR_SIZE),
#                    'Detailed Description Vector': normalize_vector_whole(game.get('Detailed Description Vector', []), VECTOR_SIZE),
#                    'About the Game Vector': normalize_vector_whole(game.get('About the Game Vector', []), VECTOR_SIZE),
#                    'Short Description Vector': normalize_vector_whole(game.get('Short Description Vector', []), VECTOR_SIZE),
#                    'Metadata Vector': normalize_vector_whole(game.get('Metadata Vector', []), VECTOR_SIZE),
#                    'Excluded Titles': game.get('excluded_titles'),
#                    'Release Year': game.get('release_year'),
#                    'Has Metacritic Score': game.get('has_metacritic_score'),
#                    'Hardware Analysis': json.dumps(game.get('hardware_analysis')),
#                    'Vector Norms': json.dumps(game.get('vector_norms'))
#                })
#
#                success_count += 1
#
#                if success_count % batch_size == 0:
#                    connection.commit()
#                    database_logger.info(f"Committed batch of {batch_size} records.")
#
#            except Exception as e:
#                error_count += 1
#                database_logger.error(f"Error while inserting data for game with App ID {game.get('App ID')}. Error: {e}")
#                connection.rollback()
#
#        connection.commit()
#
#        if error_count == 0:
#            database_logger.info(f"Successfully imported all {success_count} games from the JSONL/GZ file.")
#        else:
#            database_logger.warning(f"Import completed with {success_count} successes and {error_count} errors.")
#
#        database_logger.info(f"Total games without valid release date: {missing_dates_count}")
#        database_logger.info(f"------------End of data importing------------\n")
#
#    except Exception as e:
#        database_logger.error(f"Critical error: {e}")
#        if connection:
#            connection.rollback()
#    finally:
#        if connection:
#            return_connection(connection)
#
#folder_path = '../GameRecommendation/Data/GamesData'
#all_files = os.listdir(folder_path)
#
#base_names = sorted(set(
#    re.sub(r"\.jsonl(\.gz)?$", "", f)
#    for f in all_files
#    if re.match(r"steam_games_processed_vector_part\d+\.jsonl(\.gz)?$", f)
#))
#
#for base_name in base_names:
#    print(base_name)
#    insert_data_from_json_file(base_name)
