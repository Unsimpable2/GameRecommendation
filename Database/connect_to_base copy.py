import psycopg2
from psycopg2 import sql
import json

# Parametry połączenia
host = "localhost"  # lub adres IP serwera, jeśli używasz zdalnej bazy danych
port = "5432"  # Domyślny port PostgreSQL
dbname = "twoja_baza_danych"  # Nazwa Twojej bazy danych
user = "twoja_nazwa_uzytkownika"  # Użytkownik PostgreSQL
password = "twoje_haslo"  # Hasło do bazy danych

# Funkcja łącząca z bazą danych
def connect_to_postgres():
    try:
        # Nawiązanie połączenia
        connection = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password
        )
        
        # Tworzenie kursora
        cursor = connection.cursor()
        
        # Wykonanie przykładowego zapytania
        cursor.execute("SELECT version();")
        
        # Pobranie wyników zapytania
        postgres_version = cursor.fetchone()
        print(f"Połączono z PostgreSQL, wersja: {postgres_version}")
        
        # Zwrócenie kursora i połączenia
        return connection, cursor

    except Exception as error:
        print(f"Błąd połączenia z PostgreSQL: {error}")
        return None, None

# Funkcja do wstawiania danych JSON do bazy danych
def insert_data_from_json(json_file):
    connection, cursor = connect_to_postgres()
    
    if connection is None or cursor is None:
        return
    
    # Wczytanie danych z pliku JSON
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Dla każdego elementu w JSON, wstawiamy go do bazy danych
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
                'Categories': json.dumps(game.get('Categories')),  # Konwersja na JSONB
                'Genres': json.dumps(game.get('Genres'))  # Konwersja na JSONB
            })

            # Zatwierdzenie transakcji
            connection.commit()

        except Exception as e:
            print(f"Błąd podczas wstawiania danych: {e}")
            connection.rollback()  # Cofnięcie transakcji w przypadku błędu
    
    # Zamykanie kursora i połączenia
    cursor.close()
    connection.close()
    print("Dane zostały wstawione i połączenie zostało zamknięte.")

# Wywołanie funkcji do wstawienia danych
insert_data_from_json('sciezka_do_pliku.json')