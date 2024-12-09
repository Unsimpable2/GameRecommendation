import psycopg2
from psycopg2 import sql
import json

host = "localhost"
port = "5432"
dbname = "twoja_baza_danych"
user = "twoja_nazwa_uzytkownika"
password = "twoje_haslo"

def connect_to_postgres():
    try:
        connection = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password
        )
        
        cursor = connection.cursor()
        
        cursor.execute("SELECT version();")
        
        postgres_version = cursor.fetchone()
        print(f"Połączono z PostgreSQL, wersja: {postgres_version}")
        
        return connection, cursor

    except Exception as error:
        print(f"Błąd połączenia z PostgreSQL: {error}")
        return None, None

def insert_data_from_json(json_file):
    connection, cursor = connect_to_postgres()
    
    if connection is None or cursor is None:
        return
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for game in data:
        try:
            query = sql.SQL("""
                INSERT INTO games (
                    app_id, game_name, type, developer, publisher, is_free, price, 
                    age_rating, detailed_description, short_description, about_the_game, 
                    minimum_requirements, recommended_requirements, categories, genres
                ) VALUES (
                    %(App ID)s, %(Game Name)s, %(Type)s, %(Developer)s, %(Publisher)s, %(Is Free)s, %(Price)s,
                    %(Age Rating)s, %(Detailed Description)s, %(Short Description)s, %(About the Game)s,
                    %(Minimum Requirements)s, %(Recommended Requirements)s, %(Categories)s, %(Genres)s
                )
                ON CONFLICT (app_id) DO NOTHING;
            """)

            cursor.execute(query, {
                'App ID': game.get('App ID'),
                'Game Name': game.get('Game Name'),
                'Type': game.get('Type'),
                'Developer': game.get('Developer'),
                'Publisher': game.get('Publisher'),
                'Is Free': game.get('Is Free'),
                'Price': game.get('Price'),
                'Age Rating': game.get('Age Rating'),
                'Detailed Description': game.get('Detailed Description'),
                'Short Description': game.get('Short Description'),
                'About the Game': game.get('About the Game'),
                'Minimum Requirements': game.get('Minimum Requirements'),
                'Recommended Requirements': game.get('Recommended Requirements'),
                'Categories': json.dumps(game.get('Categories')),
                'Genres': json.dumps(game.get('Genres'))
            })

            connection.commit()

        except Exception as e:
            print(f"Błąd podczas wstawiania danych: {e}")
            connection.rollback()
    
    cursor.close()
    connection.close()
    print("Dane zostały wstawione i połączenie zostało zamknięte.")

insert_data_from_json('sciezka_do_pliku.json')