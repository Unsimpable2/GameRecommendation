#import psycopg
#
#host = "localhost"
#port = "1234"
#dbname = "SteamGamesDB"
#user = "postgres"
#password = "admin"
#
#def create_tables():
#    try:
#        connection = psycopg.connect(
#            host = host,
#            port = port,
#            dbname = dbname,
#            user = user,
#            password = password
#        )
#        cursor = connection.cursor()
#
#        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
#
#        create_games_table_query = """
#        CREATE TABLE IF NOT EXISTS games (
#            id SERIAL PRIMARY KEY,
#            app_id INTEGER NOT NULL UNIQUE,
#            game_name TEXT,
#            type TEXT,
#            developer TEXT[],
#            publisher TEXT[],
#            is_free BOOLEAN,
#            price NUMERIC,
#            age_rating INTEGER,
#            minimum_requirements TEXT,
#            recommended_requirements TEXT,
#            categories JSONB,
#            tags JSONB,
#            genres JSONB,
#            recommendations JSONB,
#            release_date DATE,
#            release_date_days INTEGER,
#            features vector(768),
#            metadata_vector vector(768),
#            excluded_titles TEXT[],
#            release_year INTEGER,
#            has_metacritic_score BOOLEAN,
#            hardware_analysis JSONB,
#            vector_norms JSONB
#        );
#        """
#
#        cursor.execute(create_games_table_query)
#        print("The 'games' table has been created successfully.")
#
#        connection.commit()
#
#    except (Exception, psycopg.Error) as error:
#        print(f"Error while executing the query: {error}")
#
#    finally:
#        if connection:
#            cursor.close()
#            connection.close()
#            print("The connection to the database has been closed.")
#
#create_tables()
#