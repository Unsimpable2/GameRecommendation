import json

from Scripts.Database.db_connection_pool import create_connection_pool, get_connection, return_connection, close_connection_pool

def app_id_exists(conn, app_id):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM games WHERE app_id = %s LIMIT 1", (app_id,))
        return cur.fetchone() is not None

def filter_existing_appids(json_file_path):
    create_connection_pool()
    conn = get_connection()

    with open(json_file_path, "r", encoding = "utf-8") as f:
        games_list = json.load(f)

    original_count = len(games_list)

    filtered_games = [
        game for game in games_list
        if not app_id_exists(conn, game.get("appid"))
    ]

    return_connection(conn)
    close_connection_pool()

    with open(json_file_path, "w", encoding = "utf-8") as f:
        json.dump(filtered_games, f, indent = 4, ensure_ascii = False)

    removed_count = original_count - len(filtered_games)
    return removed_count, filtered_games
