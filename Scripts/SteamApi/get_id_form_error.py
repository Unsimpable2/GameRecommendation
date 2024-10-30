import re
import json
import os

def get_id_from_error(log_file_path = '../MasterDeg/Scripts/Logs/Download/error_id.log', output_json_path = '../MasterDeg/Data/IDList/steam_game_list_to_update.json'):
    app_ids = []
    
    with open(log_file_path, 'r', encoding = 'utf-8') as log_file:
        lines = log_file.readlines()
    
    for line in lines:
        error_match = re.search(r'ERROR - Error while fetching data for app_id: (\d+)', line.strip())
        
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

get_id_from_error()
