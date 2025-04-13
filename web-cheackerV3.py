from datetime import datetime
import csv
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


# +----------------------------------------------------------------
# + my module imports
# +----------------------------------------------------------------
import playwright_mainditect_v3 as playwright_mainditect
from mail import send_email
from text_struct import text_struct
import util_str
from dom_treeSt import DOMTreeSt, BoundingBox
from setup_logger import setup_logger
# +----------------------------------------------------------------
# + Constant definition
# +----------------------------------------------------------------
SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
SAVE_CSV_DIR_PATH = os.path.join(SCRIPT_PATH, "./data/cheacker_url.csv")
SAVE_JSON_DIR_PATH  = os.path.join(SCRIPT_PATH, "./data/json/")
USER_DIR_PATH = os.path.join(SCRIPT_PATH, "./user")

WORKER_THREADS_NUM = 2
PROC_MPL_SEC = 30

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


        self.csv_file_path = os.path.join(self.directory, "cheacker_url.csv")
        self.csv_file_path = os.path.abspath(self.csv_file_path)
        
        self.csv_file_path = self.csv_file_path.replace(r"\\", "/")

        self.json_dir_path = os.path.join(self.directory, "json/")

        util_str.util_handle_path(self.csv_file_path)
        util_str.util_handle_path(self.json_dir_path)

        self.load_mail_settings()

    # mail settings
    def load_mail_settings(self):
        config_pass = os.path.join(self.directory,"mail.yaml")
        logger.debug(config_pass)

        with open(config_pass)as f :
            self.yaml_file = yaml.safe_load(f)

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

def get_last_modified(url):
    try:
        response = requests.head(url)
        last_modified = response.headers.get('Last-Modified')
        if last_modified:

            last_modified_datetime = datetime.strptime(last_modified, DEFAULT_DATEFORMAT)
            formatted_last_modified = last_modified_datetime.strftime("%Y%m%d")
            
            logger.debug(formatted_last_modified, type(formatted_last_modified))
            return formatted_last_modified
    except Exception as e:
        logger.warning(e)

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


class CSVManager:
    def __init__(self, file_path, csv_column_dict):
        self.file_path = file_path
        self.csv_column = csv_column_dict
        self.max_column = len(csv_column_dict)
        self.csv_df = self.read_csv_with_padding()
        self.url_column_list = self.csv_df.iloc[:, CSV_COLUMN["url"]].tolist()
        self.before_csv_df = self.csv_df.copy()
        logger.info(f"{self.csv_df}")

    def read_csv_with_padding(self) -> pd.DataFrame :
        """
        Read a CSV file and pad missing columns with None values.

        Returns:
            pandas.DataFrame: DataFrame containing the CSV data with padded columns.

        """
        try:
            # CSVファイルを読み込む
            df = pd.read_csv(self.file_path, header=None, encoding='utf-8')
            
            # カラム数がnum_columnsに足りない場合、補完する
            if len(df.columns) < self.max_column :
                logger.debug("column is too short and add column")

                padding_needed = self.max_column - len(df.columns)
                padding = [[ 0 ] * padding_needed for _ in range(len(df))]
                df = pd.concat([df, pd.DataFrame(padding, columns=range(len(df.columns), self.max_column))], axis=1)
            
            # URLカラムからエンコーディングされた文字列を削除する
            df[CSV_COLUMN["url"]] = df[CSV_COLUMN["url"]].apply(lambda x: unicodedata.normalize('NFKD', x) if isinstance(x, str) else x)

            # dateframeの値に欠損値（NaN)を""に置換
            df = df.fillna("").astype(str)

            return df
        except pd.errors.EmptyDataError:
            logger.warning("指定されたファイルが空です。空ファイル内に空のデータを追加します。")
            empty_data = [[ 0 ] * self.max_column]
            pd.DataFrame(empty_data).to_csv(self.file_path, index=False, header=False)  # 空ファイル内に空のデータを追加
            return pd.DataFrame(empty_data)
        
    def write_csv_update_date(self) -> None:
        self.csv_df.iloc[:, CSV_COLUMN["run_code"]] = self.get_str_datetime()
        self.csv_df.to_csv(self.file_path, index=False, header=False)

    def write_csv_updateValues( self ,
                                content_hash_txt :str ,
                                index_num : int,
                                css_selector : str,
                                chk_url : str ) -> None:
        self.csv_df.at[index_num, CSV_COLUMN["updated_datetime"]] = self.get_str_datetime()
        self.csv_df.at[index_num, CSV_COLUMN["result_vl"]] = content_hash_txt
        self.csv_df.at[index_num, CSV_COLUMN["css_selector"]] = css_selector
        if chk_url != self.csv_df.at[index_num, CSV_COLUMN["url"]] :
            self.csv_df.at[index_num, CSV_COLUMN["url"]] = chk_url
        logger.info(f" ## update ## - index : {index_num} - {content_hash_txt}")

    @staticmethod
    def get_str_datetime() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def chk_diff(self) -> list:
        # diff chack of dataflame
        diff_column = self.csv_df.iloc[:, CSV_COLUMN["result_vl"] ] != self.before_csv_df.iloc[:, CSV_COLUMN["result_vl"] ]

        result = self.csv_df[diff_column]

        diff_df = [row[CSV_COLUMN["url"]] for row in result.values.tolist()]
        logger.info(diff_df)
        return diff_df

    def get_record_as_dict(self, index: int) -> dict:
        return {col_name: self.csv_df.at[index, col_idx] for col_name, col_idx in self.csv_column.items()}

    def update_record_from_dict(self, index: int, record_dict: dict) -> None:
        for key, value in record_dict.items():
            if key in self.csv_column:
                self.csv_df.at[index, self.csv_column[key]] = value
            else :
                logger.warning(f"column not found for {key}")

    def __getitem__(self, index_column):
        index, column = index_column
        return self.csv_df.at[index, CSV_COLUMN[column]]

    def __setitem__(self, index_column, value):
        index, column = index_column
        self.csv_df.at[index, CSV_COLUMN[column]] = value

# csv function end ---------------------------------------------------------------- 

def scraping_mainditect(url_data : dict) -> DOMTreeSt | None:
    try:
        url = url_data['url']
        web_type = url_data['web_page_type']
        rescored_candidate = asyncio.run(playwright_mainditect.test_main(url))

        return rescored_candidate
    except Exception as e:
        logger.warning(f"{e}")

def choice_content(url_data : dict) -> DOMTreeSt | None:
    url = url_data['url']
    css_selector = url_data['css_selector']
    web_type = url_data["web_page_type"]
    try:
        rescored_candidate = asyncio.run(playwright_mainditect.choice_content(url,css_selector,web_type))
        return rescored_candidate
    except Exception as e:
        logger.exception()

# Worker function to process a single URL
def process_url(url : str, 
                index_num : int, 
                csv_manager : CSVManager,  
                error_list : list
                ):
    try:

        now_sec = datetime.now()

        css_selector = csv_manager[index_num, "css_selector"]
        run_code_time = csv_manager[index_num, "run_code"]
        full_scan_datetime = csv_manager[index_num, "full_scan_datetime"]
        bef_web_type = csv_manager[index_num,"web_page_type"]

        diff_days = (safe_parse_datetime(run_code_time) - safe_parse_datetime(full_scan_datetime)).days
        logger.debug(f"scan datatime : {safe_parse_datetime(run_code_time)} type:{type(run_code_time)}")
        logger.debug(f"full datatime : {safe_parse_datetime(full_scan_datetime)} type:{type(full_scan_datetime)}")
        logger.info(f"diff day : {diff_days} url : {url}")

        logger.debug(f"web type {bef_web_type} {type(bef_web_type)}")

        result_flg = False
        update_flg = False

        # last_modified = get_last_modified(url)
        # if last_modified:
        #     if csv_df.at[index_num, CL_RESULT_VL] != last_modified or csv_df.at[index_num, CL_RESULT_VL] is None:
        #         log_print.info(f"{csv_df.at[index_num, CL_RESULT_VL]} is not {last_modified}) ")
        #         write_csv_updateValues(last_modified, csv_df, index_num)
        #         log_print.info(f"Updated URL for modified : {url}")
        #         result_flg = True


        if not css_selector or diff_days >= 4:
            # ----------------------------------------------------------------
            # full scan 
            # ----------------------------------------------------------------
            logger.info(f"FULL SCAN URL: {url}, index: {index_num}")
            rescored_candidate = scraping_mainditect(csv_manager.get_record_as_dict(index_num))
            if rescored_candidate:
                csv_manager[index_num, "full_scan_datetime"] = get_Strdatetime()
                csv_manager[index_num, "web_page_type"] = rescored_candidate.web_type
                update_flg = True
                result_flg = True
            else:
                logger.info("Full scan returned None")
                error_list.append([url, "Full scan returned None"])
                return
        else:
            # -----------------------------------------------------------------
            # selecter choice scan
            # -----------------------------------------------------------------
            logger.info(f"CHOICE SCAN URL: {url}, index: {index_num}") 
            try:
                rescored_candidate = choice_content(csv_manager.get_record_as_dict(index_num))
                proc_time = datetime.now() - now_sec
                if proc_time.total_seconds() > PROC_MPL_SEC:
                    error_list.append([url, f"Processing time exceeded {PROC_MPL_SEC} sec -> {proc_time.total_seconds()} sec"])
                update_flg = True
            except Exception as e:
                logger.error(e)
                return

        # ----------------------------------------------------------------
        # result process
        # ----------------------------------------------------------------
        if rescored_candidate:
            content_hash_text = hashlib.sha256(str(rescored_candidate.links).encode()).hexdigest()
            logger.debug("hash_text: %s", content_hash_text)
            if csv_manager[index_num, "result_vl"] != content_hash_text:

                chk_url = rescored_candidate.url

                # if url == chk_url:
                css_selector = rescored_candidate.css_selector
                
                # save_json(rescored_candidate.to_dict, chk_url)
                # log_print("■save_json")
                logger.info(f"{url} : webtype : {rescored_candidate.web_type}")

                csv_manager.write_csv_updateValues(content_hash_text, index_num, css_selector, chk_url)
                result_flg = True
        else:
            logger.error("Choice content is None")
            error_list.append([url, "Choice content None"])
            csv_manager[index_num, "full_scan_datetime"] = ""
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)  # 例外のトレースバックを取得
        last_entry = tb[-1]  # 最後のエントリ（エラーが発生した行）
        logger.error(f"Error processing URL {url}: {e}{last_entry.lineno}")
        error_list.append([url, e,last_entry.line,last_entry.lineno])
    
#     return result_flg, update_flg
        return None

def worker( q : queue.Queue,
            csv_manager : CSVManager,
            error_list : list
            ):
    while True:
        try:
            url = q.get(timeout=10)
        except queue.Empty:
            logger.debug("Queue is empty, exiting worker")
            break
        
        index_num = csv_manager.url_column_list.index(url)
        if url is None:
            break

        # result_flg, update_flg = process_url(url, index_num, csv_manager, error_list)
        # log_print.debug(f"Worker flags - Result: {result_flg}, Update: {update_flg}")
        process_url(url, index_num, csv_manager, error_list)
        q.task_done()


def start_workers(q : queue.Queue, 
                  csv_manager : CSVManager, 
                  error_list : list 
                  ):
    threads = []
    for _ in range(WORKER_THREADS_NUM):
        thread = threading.Thread(target=worker, args=(q, csv_manager, error_list))
        thread.daemon = True
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()


def main():
    if os.path.isdir("temp_image"):
        shutil.rmtree("temp_image")
    
    user = User("jav")
    util_str.util_handle_path(user.csv_file_path)

    csv_manager = CSVManager(user.csv_file_path, CSV_COLUMN)
    
    error_list = []
    
    q_pool = queue.Queue()

    for url in csv_manager.csv_df.iloc[:, CSV_COLUMN["url"]]:
        if url:
            q_pool.put(url)

    start_workers(q_pool, csv_manager, error_list)
    
    csv_manager.write_csv_update_date()
    diff_urls = csv_manager.chk_diff()

    file_list = asyncio.run(playwright_mainditect.save_screenshot(diff_urls, save_dir="temp_image"))
    asyncio.run(playwright_mainditect.save_screenshot(diff_urls, save_dir="data/view",width=1920))

    
    if error_list:
        logger.info("-------- ERROR list output -----------")
        for error_msg in error_list:
            logger.warning(error_msg)

        traceback.print_exc()

    if diff_urls:
        body = text_struct.generate_html(diff_urls, file_list)
        user.send_resultmail(body, body_type="html", image_list=file_list)
    
    shutil.rmtree("temp_image")

    logger.info(f"{csv_manager.csv_df}")

if __name__ == "__main__":
    main()

 