import logging
import os
from psycopg2 import pool

def setup_logger():
    log_dir = '../GameRecommendation/Logs/Database'
    os.makedirs(log_dir, exist_ok = True)
    log_file_path = os.path.join(log_dir, 'database_connection.log')
    logger = logging.getLogger(__name__)
    handler = logging.FileHandler(log_file_path, mode = 'a')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

logger = setup_logger()

db_pool = None

def create_connection_pool(minconn = 1, maxconn = 10):
    global db_pool
    try:
        db_pool = pool.SimpleConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            host = "localhost",
            port = "1234",
            dbname = "SteamGamesDB",
            user = "postgres",
            password = "admin"
        )
        if db_pool:
            logger.info("Connection pool created successfully.")
    except Exception as e:
        logger.error(f"Failed to create connection pool: {e}")
        raise

def get_connection():
    global db_pool
    if not db_pool:
        raise Exception("Connection pool has not been initialized.")
    logger.info("Connection retrieved from pool.")
    return db_pool.getconn()

def return_connection(connection):
    global db_pool
    if db_pool:
        db_pool.putconn(connection)
        logger.info("Connection returned to pool.")

def close_connection_pool():
    global db_pool
    if db_pool:
        db_pool.closeall()
        logger.info("Connection pool closed.")
