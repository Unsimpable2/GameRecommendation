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
        CREATE TABLE games (
            app_id INTEGER PRIMARY KEY,
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
            genres JSONB
        );
        """

        cursor.execute(create_table_query)

        connection.commit()

        print("Tabela 'people' została utworzona pomyślnie.")

    except (Exception, psycopg.Error) as error:
        print(f"Błąd podczas wykonywania zapytania: {error}")

    finally:
        if connection:
            cursor.close()
            connection.close()
            print("Połączenie z bazą danych zostało zamknięte.")

create_table()