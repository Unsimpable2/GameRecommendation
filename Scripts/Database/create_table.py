import psycopg

host = "localhost"
port = "1234"
dbname = "SteamGamesDB"
user = "postgres"
password = "admin"

def create_table():
    try:
        connection = psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password
        )

        cursor = connection.cursor()

        create_table_query = """
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
            app_id INTEGER NOT NULL,
            game_name TEXT,
            type TEXT,
            developer TEXT[],
            publisher TEXT[],
            is_free BOOLEAN,
            price TEXT,
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
            release_date DATE
        );
        """

        cursor.execute(create_table_query)

        connection.commit()

        print("The 'games' table has been created successfully.")

    except (Exception, psycopg.Error) as error:
        print(f"Error while executing the query: {error}")

    finally:
        if connection:
            cursor.close()
            connection.close()
            print("The connection to the database has been closed.")

create_table()
