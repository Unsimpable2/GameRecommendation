import re
import json

def extract_app_ids(log_file_path, output_json_path):
    app_ids = []
    
    with open(log_file_path, 'r') as log_file:
        lines = log_file.readlines()
    
    for i in range(len(lines) - 1):
        error_line = lines[i].strip()
        warning_line = lines[i+1].strip()
        
        error_match = re.search(r'ERROR - Error while fetching data for app_id: (\d+)', error_line)
        warning_match = re.search(r'WARNING - Failed to fetch details for app_id: (\d+)', warning_line)
        
        if error_match and warning_match:
            app_id_error = error_match.group(1)
            app_id_warning = warning_match.group(1)
            
            if app_id_error == app_id_warning:
                app_ids.append({"appid": int(app_id_error)})
    
    with open(output_json_path, 'w') as json_file:
        json.dump(app_ids, json_file, indent = 4)

    open(log_file_path, 'w').close()

log_file_path = '../MasterDeg/Scripts/Logs/Download/error_id.log'
output_json_path = '../MasterDeg/Data/IDList/id_log_error.json'

extract_app_ids(log_file_path, output_json_path)
