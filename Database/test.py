import psycopg
import json


host = "localhost"
port = "1234"
dbname = "SteamGamesDB"
user = "postgres"
password = "admin"

def connect_to_postgres():
    try:
        connection = psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password
        )
        cursor = connection.cursor()

        print("Połączono z PostgreSQL")
        return connection, cursor

    except Exception as error:
        print(f"Błąd połączenia z PostgreSQL: {error}")
        return None, None

def insert_people_from_json(json_file):
    connection, cursor = connect_to_postgres()

    if connection is None or cursor is None:
        return

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for person in data:
        try:
            query = """
                INSERT INTO people (name, age) 
                VALUES (%s, %s);
            """
            cursor.execute(query, (person['name'], person['age']))

            connection.commit()

        except Exception as e:
            print(f"Błąd podczas wstawiania danych: {e}")
            connection.rollback()

    cursor.close()
    connection.close()
    print("Dane zostały wstawione i połączenie zostało zamknięte.")

insert_people_from_json('../MasterDeg/Database/test.json')