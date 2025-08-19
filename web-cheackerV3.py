from datetime import datetime
import pandas as pd
import json
import os , sys
import hashlib
import queue
import threading
import numpy as np
import requests
import asyncio
import shutil
import traceback
import re
import json
import html

# +----------------------------------------------------------------
# + my module imports
# +----------------------------------------------------------------
from content_extractor import run_full_scan_standalone, run_quick_scan_standalone
from mail import send_email
from text_struct import text_struct
import util_str
from content_extractor import DOMTreeSt, BoundingBox
from setup_logger import setup_logger
from content_extractor import save_screenshot
# +----------------------------------------------------------------
# + Constant definition
# +----------------------------------------------------------------
SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
SAVE_CSV_DIR_PATH = os.path.join(SCRIPT_PATH, "./data/cheacker_url.csv")
SAVE_JSON_DIR_PATH  = os.path.join(SCRIPT_PATH, "./data/json/")
USER_DIR_PATH = os.path.join(SCRIPT_PATH, "./user")

# カレントディレクトリをpythonパスに追加する
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# +----------------------------------------------------------------
# pandas option 
# +----------------------------------------------------------------
# 表示オプションを変更して、すべての行と列を表示する
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)



# +----------------------------------------------------------------
# logging settings
# +----------------------------------------------------------------
LOGGER_DATEFORMAT = "%Y%m%d_%H%M%S"
nowtime = datetime.now()
formatted_now = nowtime.strftime(LOGGER_DATEFORMAT)

logger = setup_logger("web-cheacker",log_file=f"./log/web-chk_{formatted_now}.log")

logger.debug(SCRIPT_PATH)


# +----------------------------------------------------------------
# + User class 
# +----------------------------------------------------------------
import yaml

class User:
    def __init__(self, directory):
        util_str.util_handle_path("./users/")

        self.directory = os.path.join("users",directory)


        self.data_file_path = os.path.join(self.directory, "cheacker_url.jsonl")
        self.data_file_path = os.path.abspath(self.data_file_path)
        self.data_file_path = self.data_file_path.replace(r"\\", "/")

        self.json_dir_path = os.path.join(self.directory, "json/")

        util_str.util_handle_path(self.data_file_path)
        util_str.util_handle_path(self.json_dir_path)

        self.load_mail_settings()
        self.load_app_config()

    # mail settings
    def load_mail_settings(self):
        config_pass = os.path.join(self.directory,"mail.yaml")
        logger.debug(config_pass)

        with open(config_pass)as f :
            self.yaml_file = yaml.safe_load(f)

    def load_app_config(self):
        """アプリケーション全体の設定を読み込む"""
        config_path = os.path.join(self.directory, "config.yaml")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
                logger.info(f"Loaded app config from {config_path}")
        except FileNotFoundError:
            logger.warning(f"App config file not found at {config_path}. Using default behaviors.")
            self.config = {} # 設定ファイルがなくてもエラーにならないように空の辞書をセット
        except Exception as e:
            logger.error(f"Error loading app config: {e}")
            self.config = {}

    def send_resultmail(self, body, body_type, image_list=[]):
        if self.yaml_file is not None:
            send_email(
                self.yaml_file,
                self.yaml_file["gmail"]["receiver_mail"],
                body=body,
                body_type=body_type,
                image_list=image_list
            )

        else : logger.warning("not send mail")


# +----------------------------------------------------------------
# + NotificationManager class
# +----------------------------------------------------------------
class NotificationManager:
    def __init__(self, user: User):
        self.user = user
        self.config = user.config

    def send_update_notification(self, diff_urls: list):
        if not diff_urls:
            return

        logger.info(f"Processing update notifications for {len(diff_urls)} URLs...")
        
        notification_type = self.config.get('notification', {}).get('type', 'none')
        if notification_type != 'email':
            logger.info("Email notification is disabled in config. Skipping.")
            return

        # スクリーンショットの生成
        file_list = []
        ss_config = self.config.get('screenshot', {})
        if ss_config.get('enabled', False):
            temp_dir = ss_config.get('temporary_dir', 'temp_image')
            perm_dir = ss_config.get('permanent_dir', 'data/view')
            email_width = ss_config.get('email_width', 500)
            perm_width = ss_config.get('permanent_width', 1920)

            logger.info(f"Generating screenshots for email to {temp_dir}...")
            file_list = asyncio.run(save_screenshot(diff_urls, save_dir=temp_dir, width=email_width))
            logger.info(f"Generating screenshots for permanent storage to {perm_dir}...")
            asyncio.run(save_screenshot(diff_urls, save_dir=perm_dir, width=perm_width))

        # メール本文の生成と送信
        logger.info("Generating HTML body for email...")
        body = text_struct.generate_html(diff_urls, file_list)
        logger.info("Sending update notification email...")
        self.user.send_resultmail(body, body_type="html", image_list=file_list)

    def send_error_notification(self, error_list: list):
        if not error_list:
            return

        logger.info(f"Processing error notifications for {len(error_list)} errors...")
        
        notification_config = self.config.get('notification', {})
        if notification_config.get('type', 'none') != 'email' or not notification_config.get('notify_on_error', False):
            logger.info("Error notification via email is disabled in config. Skipping.")
            return

        error_body_lines = ["<h1>Web Checker Error Report</h1>", "<ul>"]
        for error_msg in error_list:
            error_body_lines.append(f"<li>{html.escape(str(error_msg))}</li>")
        error_body_lines.append("</ul>")
        
        logger.info("Sending error report email...")
        self.user.send_resultmail("\n".join(error_body_lines), body_type="html")

# +----------------------------------------------------------------
# + json function
# +----------------------------------------------------------------
def save_json(data : dict, 
              url : str, 
              directory=SAVE_JSON_DIR_PATH):
    """
    辞書型のデータをJSONファイルとして保存する
    
    Args:
        data (dict): 保存するデータ
        url (str): データに対応するURL
        directory (str): JSONファイルを保存するディレクトリのパス
    Retrun: 
        None
    """
    domain = util_str.get_domain(url)
    file_path = os.path.join(directory, f"{domain}.json")
    util_str.util_handle_path(file_path)  # ファイルを作成または取得する
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# +----------------------------------------------------------------
# datetime edit function 
# +----------------------------------------------------------------
DEFAULT_DATETIME = "19700101 00:00"
DEFAULT_DATEFORMAT = "%Y%m%d %H:%M"
# 正規表現と対応する strptime フォーマットの辞書
DATE_FORMATS = [
    (re.compile(r"^\d{4}\d{2}\d{2} \d{2}:\d{2}:\d{2}$"), "%Y%m%d %H:%M:%S"),
    (re.compile(r"^\d{4}\d{2}\d{2} \d{2}:\d{2}$"), "%Y%m%d %H:%M"),
    (re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"), "%Y-%m-%d %H:%M:%S"),
    (re.compile(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}$"), "%Y/%m/%d %H:%M"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d"),
    (re.compile(r"^\d{2}/\d{2}/\d{4}$"), "%m/%d/%Y"),
    (re.compile(r"^\d{4}/\d{2}/\d{2}$"), "%Y/%m/%d"),
    (re.compile(r"^\d{2}-\d{2}-\d{4}$"), "%d-%m-%Y"),
    (re.compile(r"^\d{2}:\d{2}:\d{2}$"), "%H:%M:%S"),
    (re.compile(r"^\d{2}:\d{2}$"), "%H:%M"),
]

def get_Strdatetime() -> str:
    nowtime = datetime.now()
    formatted_now = nowtime.strftime(DEFAULT_DATEFORMAT)

    return formatted_now

def exchange_datetime(date_string : str) -> datetime :
    return datetime.strptime(date_string, DEFAULT_DATEFORMAT )

def test_datetime():    
    date_string = "20240326"

    print(exchange_datetime(date_string))
    print(get_Strdatetime())

def detect_datetime_format(date_str):
    for pattern, fmt in DATE_FORMATS:
        if pattern.match(date_str):
            # logger.debug("format found")
            return fmt
    return None  # 判別できなかった場合

def safe_parse_datetime(date_str, default_datetime=DEFAULT_DATETIME):
    """
    Safely parse a datetime string. If parsing fails, use the default datetime.

    Args:
        date_str (str): The datetime string to parse.
        date_format (str): The expected datetime format.
        default_datetime (str): The default datetime string to use if parsing fails.

    Returns:
        datetime: A parsed datetime object.
    """

    fmt = detect_datetime_format(date_str)

    if fmt :
        return datetime.strptime(date_str, fmt)
    else :
        logger.warning(f"Invalid datetime format for '{date_str}'. Using default: {default_datetime}")
        return datetime.strptime(default_datetime, DEFAULT_DATEFORMAT)


# +----------------------------------------------------------------
#   Last-Modified function
# +----------------------------------------------------------------

from email.utils import parsedate_to_datetime

def get_last_modified(url: str) -> str | None:
    """
    URLのLast-Modifiedヘッダを取得し、単純な文字列として返す。
    タイムゾーンは考慮せず、日付と時刻の文字列表現として扱う。
    """
    try:
        # タイムアウトを設定して、応答がない場合に長時間待たないようにする
        response = requests.head(url, timeout=10)
        response.raise_for_status() # 200番台以外のステータスコードで例外を発生
        
        last_modified_header = response.headers.get('Last-Modified')
        if last_modified_header:
            # 例: "Wed, 21 Oct 2015 07:28:00 GMT" -> datetimeオブジェクトに変換
            dt_object = parsedate_to_datetime(last_modified_header)
            # datetimeオブジェクトを単純な文字列にフォーマットして返す
            return dt_object.strftime("%Y-%m-%d %H:%M:%S")
            
    except requests.RequestException as e:
        logger.debug(f"Could not get Last-Modified for {url}: {e}")
    except (TypeError, ValueError) as e:
        logger.debug(f"Could not parse Last-Modified header for {url}: {e}")
        
    return None

# + ----------------------------------------------------------------
#  remove encoded chars
# + ----------------------------------------------------------------
import re

def remove_encoded_chars(url):
    encoded_pattern = r'%[0-9A-F]{2}'
    cleaned_url = re.sub(encoded_pattern, '', url)
    return cleaned_url


# +----------------------------------------------------------------
# csv function 
# +----------------------------------------------------------------
from urllib.parse import unquote
import unicodedata

CSV_COLUMN = { "url" : 0, # scraping url
               "run_code" : 1, # datetime for code of the run for
               "result_vl" : 2 ,  
               "updated_datetime" : 3, 
               "full_scan_datetime"  : 4, 
               "css_selector" : 5,
               "web_page_type" : 6,
}


class DataManager:
    def __init__(self, file_path):
        self.file_path = file_path
        self.lock = threading.Lock()
        try:
            with self.lock:
                self.df = pd.read_json(self.file_path, lines=True, orient='records')
        except (FileNotFoundError, ValueError):
            self.df = pd.DataFrame(columns=[
                "url", "run_code", "result_vl", "updated_datetime", 
                "full_scan_datetime", "css_selector_list", "web_page_type"
            ])
        
        if 'css_selector_list' not in self.df.columns:
            self.df['css_selector_list'] = [[] for _ in range(len(self.df))]

        self.df = self.df.fillna({
            'web_page_type': '',
            'result_vl': '',
            'full_scan_datetime': ''
        })
        self.df['css_selector_list'] = self.df['css_selector_list'].apply(lambda x: x if isinstance(x, list) else [])

        self.before_df = self.df.copy()
        logger.info(f"Loaded data:\n{self.df}")

    def get_record_as_dict(self, index: int) -> dict:
        return self.df.loc[index].to_dict()

    def update_record_from_dom_tree(self, index: int, dom_tree: DOMTreeSt):
        record = {
            "result_vl": hashlib.sha256(str(dom_tree.links).encode()).hexdigest(),
            "updated_datetime": get_Strdatetime(),
            "css_selector_list": dom_tree.css_selector_list,
            "web_page_type": dom_tree.web_type,
            "url": dom_tree.url
        }
        for key, value in record.items():
            self.df.at[index, key] = value
        logger.info(f" ## update ## - index : {index}")
        
    def update_scan_result(self, index: int, dom_tree: DOMTreeSt):
        """
        スキャン成功時の結果をまとめてDataFrameに書き込むメソッド。
        """
        new_hash = hashlib.sha256(str(dom_tree.links).encode()).hexdigest()
        
        logger.info(f" ## UPDATE ## - index : {index} - {new_hash}")
        logger.debug(f"Updating with selectors: {dom_tree.css_selector_list}")

        self.df.at[index, "result_vl"] = new_hash
        self.df.at[index, "updated_datetime"] = get_Strdatetime()
        self.df.at[index, "css_selector_list"] = dom_tree.css_selector_list
        self.df.at[index, "web_page_type"] = dom_tree.web_type
        
        # URLがリダイレクト等で変更された場合に対応
        if dom_tree.url != self.df.at[index, "url"]:
            self.df.at[index, "url"] = dom_tree.url

    def update_full_scan_timestamp(self, index: int):
        """Fullスキャンのタイムスタンプのみを更新する"""
        self.df.at[index, "full_scan_datetime"] = get_Strdatetime()

    def clear_scan_data(self, index: int):
        """スキャン失敗時に、次回のFullスキャンを促すためにデータをクリアする"""
        logger.warning(f"Clearing scan data for index: {index} to force full scan next time.")
        self.df.at[index, "css_selector_list"] = []
        self.df.at[index, "full_scan_datetime"] = ""

    def save_data(self):
        with self.lock:
            self.df['run_code'] = get_Strdatetime()
            self.df.to_json(self.file_path, orient='records', lines=True, force_ascii=False)

    def chk_diff(self) -> list:
        # result_vl列を比較して差分を検出
        diff_mask = self.df['result_vl'] != self.before_df['result_vl']
        diff_urls = self.df.loc[diff_mask, 'url'].tolist()
        logger.info(f"Found {len(diff_urls)} updated URLs: {diff_urls}")
        return diff_urls

# csv function end ---------------------------------------------------------------- 


# Worker function to process a single URL
def process_url(url: str, 
                index_num: int, 
                data_manager: DataManager, 
                error_list: list,
                config: dict
                ):
    try:
        # ▼▼▼ 処理開始時刻を記録 ▼▼▼
        start_time = datetime.now()
        
        record = data_manager.get_record_as_dict(index_num)

        # Last-Modifiedによる高速チェック
        # last_modified = get_last_modified(url)
        # if last_modified:
        #     if record.get('result_vl') != last_modified:
        #         data_manager.update_with_last_modified(index_num, last_modified)
        #         return 
        #     else:
        #         logger.debug(f"Skipping DOM check for {url} due to unchanged Last-Modified header.")
        #         return
        
        # --- Last-Modifiedが利用できない場合、通常のDOMスキャン処理に進む ---
        css_selector_list = record.get('css_selector_list', [])
        full_scan_datetime_str = record.get('full_scan_datetime', '')

        diff_days = 99
        if full_scan_datetime_str:
            try:
                diff_days = (datetime.now() - safe_parse_datetime(full_scan_datetime_str)).days
            except TypeError:
                logger.warning(f"Could not parse datetime: {full_scan_datetime_str}")

        rescored_candidate = None
        # ----------------------------------------------------------------
        # --- Quickスキャン試行 ---
        # ----------------------------------------------------------------
        if css_selector_list and diff_days < 4:
            logger.info(f"QUICK SCAN URL: {url}, index: {index_num}")
            rescored_candidate = asyncio.run(
                run_quick_scan_standalone(
                    url=url, 
                    css_selector_list=css_selector_list, 
                    webtype_str=record['web_page_type'])
            )
        # ----------------------------------------------------------------
        # --- Fullスキャン (Quickスキャンしなかった、または失敗した場合) ---
        # ----------------------------------------------------------------
        if not rescored_candidate:
            if css_selector_list:
                logger.info(f"Quick scan failed. Falling back to FULL SCAN for URL: {url}")
            else:
                logger.info(f"FULL SCAN URL: {url}, index: {index_num}")
            
            rescored_candidate = asyncio.run(
                run_full_scan_standalone(
                    url=record['url'], 
                    arg_webtype=record['web_page_type'])
            )
            
            if rescored_candidate:
                if rescored_candidate.is_empty_result:
                    logger.info(f"Full scan identified {url} as an empty result page.")
                    error_list.append([url, "Empty result page detected"])
                    data_manager.clear_scan_data(index_num) # 次回もFullスキャンさせる
                    return
                data_manager.update_full_scan_timestamp(index_num)
            else:
                logger.info("Full scan returned None")
                error_list.append([url, "Full scan returned None"])
                data_manager.clear_scan_data(index_num) # 次回もFullスキャンさせる
                return

        # ----------------------------------------------------------------
        # --- 結果処理 (共通) ---
        # ----------------------------------------------------------------
        if rescored_candidate:
            new_hash = hashlib.sha256(str(rescored_candidate.links).encode()).hexdigest()
            if rescored_candidate.is_empty_result:
                logger.info(f"Quick scan identified {url} as an empty result page.")
                error_list.append([url, "Empty result page detected"])
                data_manager.clear_scan_data(index_num) # 次回もFullスキャンさせる
                return
            if record['result_vl'] != new_hash:
                data_manager.update_scan_result(index_num, rescored_candidate)
        else:
            logger.error(f"Scan process resulted in None for URL: {url}")
            error_list.append([url, "Scan process resulted in None"])
            data_manager.clear_scan_data(index_num)

        # ▼▼▼ 処理の最後にタイムアウトをチェック ▼▼▼
        duration = (datetime.now() - start_time).total_seconds()
        timeout_sec = config.get('scan', {}).get('timeout_per_url', 60)
        if duration > timeout_sec:
            timeout_msg = f"Processing time exceeded {timeout_sec} sec -> {duration:.2f} sec"
            logger.warning(f"TIMEOUT for {url}: {timeout_msg}")
            error_list.append([url, timeout_msg])
            
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        last_entry = tb[-1]
        logger.error(f"Error processing URL {url}: {e} at line {last_entry.lineno}")
        error_list.append([url, e, last_entry.line, last_entry.lineno])


def worker( q : queue.Queue,
            data_manager: DataManager,
            error_list : list,
            config: dict
            ):
    while True:
        try:
            url,index_num = q.get(timeout=10)
        except queue.Empty:
            logger.info("Queue is empty, worker is shutting down.")
            break

        process_url(url, index_num, data_manager, error_list, config)
        q.task_done()


def start_workers(q : queue.Queue, 
                  data_manager : DataManager, 
                  error_list : list,
                  config: dict
                  ):
    threads = []
    worker_threads_num = config.get('scan', {}).get('worker_threads', 2)
    logger.info(f"Starting {worker_threads_num} worker threads...")
    for _ in range(worker_threads_num):
        thread = threading.Thread(target=worker, args=(q, data_manager, error_list, config))
        thread.daemon = True
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    logger.info("All worker threads have finished.")


def main():
    user = User("jav")
    config = user.config
    notification_manager = NotificationManager(user)

    # 一時フォルダのクリーンアップ
    temp_dir = config.get('screenshot', {}).get('temporary_dir', 'temp_image')
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir)

    util_str.util_handle_path(user.data_file_path)

    data_manager = DataManager(user.data_file_path)
    error_list = []
    q_pool = queue.Queue()

    for index, row in data_manager.df.iterrows():
        if row['url']:
            q_pool.put((row['url'], index))

    start_workers(q_pool, data_manager, error_list, config) 
    
    diff_urls = data_manager.chk_diff()
    data_manager.save_data()

    # --- 通知処理 ---
    notification_manager.send_update_notification(diff_urls)

    if error_list:
        logger.info("-------- ERROR list output -----------")
        for error_msg in error_list:
            logger.warning(error_msg)
        traceback.print_exc()
    
    notification_manager.send_error_notification(error_list)

    # 一時フォルダの再クリーンアップ
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir)

    logger.info(f"{data_manager.df}")

if __name__ == "__main__":
    main()

 