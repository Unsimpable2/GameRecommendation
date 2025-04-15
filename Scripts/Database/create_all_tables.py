import psycopg

host = "localhost"
port = "1234"
dbname = "SteamGamesDB"
user = "postgres"
password = "admin"

def create_tables():
    try:
        connection = psycopg.connect(
            host = host,
            port = port,
            dbname = dbname,
            user = user,
            password = password
        )
        cursor = connection.cursor()

        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        create_games_table_query = """
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
            app_id INTEGER NOT NULL UNIQUE,
            game_name TEXT,
            type TEXT,
            developer TEXT[],
            publisher TEXT[],
            is_free BOOLEAN,
            price NUMERIC,
            age_rating INTEGER,
            detailed_description TEXT,
            short_description TEXT,
            about_the_game TEXT,
            minimum_requirements TEXT,
            recommended_requirements TEXT,
            categories JSONB,
            tags JSONB,
            genres JSONB,
            recommendations INTEGER,
            release_date DATE,
            release_date_days INTEGER,
            features vector(768),
            detailed_description_vector vector(768),
            about_the_game_vector vector(768),
            short_description_vector vector(768),
            metadata_vector vector(768)
        );
        """
        cursor.execute(create_games_table_query)
        print("The 'games' table has been created successfully.")

        create_users_table_query = """
        CREATE TABLE IF NOT EXISTS users (
            user_id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            is_active BOOLEAN DEFAULT TRUE,
            is_admin BOOLEAN DEFAULT FALSE
        );
        """
        cursor.execute(create_users_table_query)
        print("The 'users' table has been created successfully.")

        create_user_game_recommendations_table_query = """
        CREATE TABLE IF NOT EXISTS user_game_recommendations (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            game_id INTEGER NOT NULL,
            user_query TEXT NOT NULL,
            recommended_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
            UNIQUE(user_id, game_id, user_query)
        );
        """
        cursor.execute(create_user_game_recommendations_table_query)
        print("The 'user_game_recommendations' table has been created successfully.")

        connection.commit()

    except (Exception, psycopg.Error) as error:
        print(f"Error while executing the query: {error}")

    finally:
        if connection:
            cursor.close()
            connection.close()
            print("The connection to the database has been closed.")

create_tables()
