import os
import sys
import logging

from Scripts.Database.db_connection_pool import create_connection_pool, get_connection, return_connection, close_connection_pool

logger = logging.getLogger("metadata_cleaner_logger")

def validate_excluded_titles(titles):
    valid_titles = []
    invalid_titles = []

    conn = None
    try:
        create_connection_pool()
        conn = get_connection()
        with conn.cursor() as cur:
            for title in titles:
                cur.execute("SELECT 1 FROM games WHERE game_name ILIKE %s LIMIT 1", (f"%{title}%",))
                if cur.fetchone():
                    valid_titles.append(title)
                else:
                    invalid_titles.append(title)
    except Exception as e:
        logger.error(f"Error while validating this title: {e}")
    finally:
        if conn:
            return_connection(conn)
            close_connection_pool()

    return valid_titles, invalid_titles