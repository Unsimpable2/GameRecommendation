import re
import os
import json

def get_id_from_error():
    app_ids = []
    log_file_path = '../GameRecommendation/Logs/Download/error_id.log'
    output_json_path = '../GameRecommendation/Data/DownloadList/steam_game_list_to_update.json'
    
    if os.path.getsize(log_file_path) == 0:
        print("Plik error_id.log is empty. End of a script.")
        return

    error_prompt = 'ERROR - Error while fetching data for app_id: '
    warning_prompt = 'WARNING - Failed to fetch details for app_id: '
    
    with open(log_file_path, 'r', encoding = 'utf-8') as log_file:
        lines = log_file.readlines()
    
    for line in lines:
        error_match = (
            re.search(error_prompt + r'(\d+)', line.strip()) or 
            re.search(warning_prompt + r'(\d+)', line.strip())
        )
        
        if error_match:
            app_id_error = error_match.group(1)
            app_ids.append({"appid": int(app_id_error)})

    if os.path.exists(output_json_path):
        with open(output_json_path, 'r+', encoding = 'utf-8') as json_file:
            content = json_file.read().strip()
            if content == "[]" or not content:
                json_file.seek(0)
                json_file.truncate()
                json.dump(app_ids, json_file, indent = 4)
            else:
                json_file.seek(0, os.SEEK_END)
                json_file.seek(json_file.tell() - 1, os.SEEK_SET)
                json_file.truncate()
                
                app_ids_str = json.dumps(app_ids, indent = 4)[1:-1]
                
                json_file.write(", ")
                json_file.write(app_ids_str)
                json_file.write("\n]")
    else:
        with open(output_json_path, 'w', encoding = 'utf-8') as json_file:
            json.dump(app_ids, json_file, indent = 4)

    open(log_file_path, 'w').close()
    print("All errors were processed and added to steam_game_list_to_update.json file")
