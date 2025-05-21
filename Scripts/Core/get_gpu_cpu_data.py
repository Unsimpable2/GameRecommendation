import os
import json
import time
import logging
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from contextlib import contextmanager
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "Data", "ComponentsData")
LOG_DIR = os.path.join(BASE_DIR, "Logs", "Update")
LOG_FILE = os.path.join(LOG_DIR, "components_update.log")

GPU_HTML_PATH = os.path.join(DATA_DIR, "GPU_list.html")
CPU_HTML_PATH = os.path.join(DATA_DIR, "CPU_list.html")
GPU_JSONL_PATH = os.path.join(DATA_DIR, "benchmark_gpu.jsonl")
CPU_JSONL_PATH = os.path.join(DATA_DIR, "benchmark_cpu.jsonl")

GPU_URL = "https://www.videocardbenchmark.net/gpu_list.php"
CPU_URL = "https://www.cpubenchmark.net/cpu_list.php"

CPU_TIERS = {
    "low": range(0, 2500),
    "medium": range(2500, 7000),
    "high": range(7000, 14000),
    "ultra": range(14000, 999999)
}

GPU_TIERS = {
    "low": range(0, 2000),
    "medium": range(2000, 6000),
    "high": range(6000, 10000),
    "ultra": range(10000, 999999)
}

def setup_component_logger():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    log_dir = os.path.join(base_dir, "Logs", "Update")
    os.makedirs(log_dir, exist_ok = True)
    log_file_path = os.path.join(log_dir, "components_update.log")

    logger = logging.getLogger("component_logger")
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    handler = logging.FileHandler(log_file_path, mode = "a", encoding = "utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

component_logger = setup_component_logger()

@contextmanager
def smart_driver():
    options = uc.ChromeOptions()
    options.headless = True
    options.add_argument("--no-sandbox")
    options.binary_location = r"C:\\Program Files (x86)\\Chromium\\chrome.exe"
    chromedriver_path = os.path.join(BASE_DIR, "chromedriver.exe")

    driver = uc.Chrome(
        options = options,
        driver_executable_path = chromedriver_path
    )
    try:
        yield driver
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def file_older_than(path, days = 7):
    if not os.path.exists(path):
        return True
    mod_time = datetime.fromtimestamp(os.path.getmtime(path))
    return datetime.now() - mod_time > timedelta(days = days)

def should_update_components(days = 7):
    return file_older_than(GPU_JSONL_PATH, days) or file_older_than(CPU_JSONL_PATH, days)

def download_html(url, save_path):
    component_logger.info(f"Opening: {url}")
    with smart_driver() as driver:
        driver.get(url)
        time.sleep(5)
        with open(save_path, "w", encoding = "utf-8") as f:
            f.write(driver.page_source)
    component_logger.info(f"Saved HTML to: {save_path}")

def parse_html_benchmark(file_path, component_type):
    with open(file_path, "r", encoding = "utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    component_logger.info(f"Parsing: {file_path}")
    table = soup.find("table", class_ = "cpulist")
    if not table:
        component_logger.warning(f"No table found in {file_path}")
        return []

    data = []
    rows = table.find_all("tr")[1:]
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 2:
            name = cols[0].text.strip()
            try:
                score = int(cols[1].text.strip().replace(",", ""))
            except ValueError:
                continue
            data.append({
                "type": component_type,
                "name": name,
                "score": score
            })
    return data

def assign_tier(score, tiers):
    for tier, score_range in tiers.items():
        if score in score_range:
            return tier
    return "unknown"

def enrich_with_tiers(data, tiers):
    for item in data:
        item["tier"] = assign_tier(item["score"], tiers)
    return data

def save_to_jsonl(path, data):
    with open(path, "w", encoding = "utf-8") as f:
        for item in data:
            f.write(json.dumps(item) + "\n")
    component_logger.info(f"Saved {len(data)} records to: {path}")

def cleanup_temp_files():
    for path in [GPU_HTML_PATH, CPU_HTML_PATH]:
        if os.path.exists(path):
            os.remove(path)
            component_logger.info(f"Deleted: {path}")

def update_component_data_if_needed(days = 7):
    if not should_update_components(days = days):
        component_logger.info("Component data is up to date, skipping update.\n")
        component_logger.info("------------End of update------------\n")
        return

    component_logger.info("Starting component update and tier assignment")

    try:
        download_html(GPU_URL, GPU_HTML_PATH)
        gpu_data = parse_html_benchmark(GPU_HTML_PATH, "GPU")
        gpu_data = enrich_with_tiers(gpu_data, GPU_TIERS)
        if gpu_data:
            save_to_jsonl(GPU_JSONL_PATH, gpu_data)
        else:
            component_logger.warning("No GPU data parsed.")
    except Exception as e:
        component_logger.error(f"GPU error: {e}")

    try:
        download_html(CPU_URL, CPU_HTML_PATH)
        cpu_data = parse_html_benchmark(CPU_HTML_PATH, "CPU")
        cpu_data = enrich_with_tiers(cpu_data, CPU_TIERS)
        if cpu_data:
            save_to_jsonl(CPU_JSONL_PATH, cpu_data)
        else:
            component_logger.warning("No CPU data parsed.")
    except Exception as e:
        component_logger.error(f"CPU error: {e}")

    cleanup_temp_files()
    component_logger.info("------------End of update------------\n")
