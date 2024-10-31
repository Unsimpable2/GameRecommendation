import shutil
import os

def backup_games_data(number):
    source_file = f'../MasterDeg/Data/GamesData/steam_games_processed_part{number}.json'
    backup_dir = '../MasterDeg/Data/Backup'
    backup_file = os.path.join(backup_dir, f'steam_games_processed_part{number}_backup.json')

    os.makedirs(backup_dir, exist_ok = True)

    if os.path.exists(backup_file):
        print(f"Backup file already exists and will be overwritten: {backup_file}")
    else:
        print(f"No existing backup found. Creating new backup: {backup_file}")

    try:
        shutil.copy2(source_file, backup_file)
        print(f"Backup created successfully: {backup_file}")
    except FileNotFoundError:
        print(f"Source file not found: {source_file}")
    except Exception as e:
        print(f"An error occurred: {e}")

backup_games_data(10)
