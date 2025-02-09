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


# +----------------------------------------------------------------
# + my module imports
# +----------------------------------------------------------------
import playwright_mainditect_v3 as playwright_mainditect
from mail import send_email
from text_struct import text_struct
import util_str

# +----------------------------------------------------------------
# + Constant definition
# +----------------------------------------------------------------
SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
SAVE_CSV_DIR_PATH = os.path.join(SCRIPT_PATH, "./data/cheacker_url.csv")
SAVE_JSON_DIR_PATH  = os.path.join(SCRIPT_PATH, "./data/json/")
USER_DIR_PATH = os.path.join(SCRIPT_PATH, "./user")

WORKER_THREADS_NUM = 2

import sys
# カレントディレクトリをpythonパスに追加する
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# +----------------------------------------------------------------
# pandas option 
# +----------------------------------------------------------------
# 表示オプションを変更して、すべての行と列を表示する
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)

PROC_MPL_SEC = 30

# +----------------------------------------------------------------
# logging settings
# +----------------------------------------------------------------
import logging

INFO = logging.INFO
DEBUG = logging.DEBUG

def setup_logging(log_level=INFO):
    # ロガーを作成
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # フォーマッターを作成
    # formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s - Line %(lineno)d')
    formatter = logging.Formatter('%(message)s - [%(filename)s][%(lineno)d Line][%(asctime)s]')
    # コンソールハンドラーを作成し、フォーマッターを設定
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # ロガーにハンドラーを追加
    logger.addHandler(console_handler)

    return logger

# set up logging
log_print = setup_logging()

log_print.info(SCRIPT_PATH)


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
        log_print.info(config_pass)

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

        else : log_print("not send mail")


# +----------------------------------------------------------------
# + json function
# +----------------------------------------------------------------
def save_json(data, url, directory=SAVE_JSON_DIR_PATH):
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
     
    # URLをデータに追加
    data['url'] = url
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# +----------------------------------------------------------------
# datetime edit function 
# +----------------------------------------------------------------
DEFAULT_DATETIME = "19700101 00:00"
DATEFORMAT = "%Y%m%d %H:%M"

def get_Strdatetime() -> str:
    nowtime = datetime.now()
    formatted_now = nowtime.strftime(DATEFORMAT)

    return formatted_now

def exchange_datetime(date_string : str) -> datetime :
    return datetime.strptime(date_string, DATEFORMAT )

def test_datetime():    
    date_string = "20240326"

    print(exchange_datetime(date_string))
    print(get_Strdatetime())

def safe_parse_datetime(date_str, date_format=DATEFORMAT, default_datetime=DEFAULT_DATETIME):
    """
    Safely parse a datetime string. If parsing fails, use the default datetime.

    Args:
        date_str (str): The datetime string to parse.
        date_format (str): The expected datetime format.
        default_datetime (str): The default datetime string to use if parsing fails.

    Returns:
        datetime: A parsed datetime object.
    """
    try:
        return datetime.strptime(date_str, date_format)
    except ValueError:
        log_print.warning(f"Invalid datetime format for '{date_str}'. Using default: {default_datetime}")
        return datetime.strptime(default_datetime, date_format)


# +----------------------------------------------------------------
#   Last-Modified function
# +----------------------------------------------------------------

def get_last_modified(url):
    try:
        response = requests.head(url)
        last_modified = response.headers.get('Last-Modified')
        if last_modified:

            last_modified_datetime = datetime.strptime(last_modified, DATEFORMAT)
            formatted_last_modified = last_modified_datetime.strftime("%Y%m%d")
            
            log_print.debug(formatted_last_modified, type(formatted_last_modified))
            return formatted_last_modified
    except Exception as e:
        log_print.warning(e)

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



CL_URL = 0
CL_RUN_CODE = 1
CL_RESULT_VL = 2
CL_UPDATED_DATETIME = 3
CL_MODIFY_DATETIME = 4 
CL_CSS_SELECTOR = 5

CSV_COLUMN = { "url" : 0, # scraping url
               "run_code" : 1, # datetime for code of the run for
               "result_vl" : 2 ,  
               "updated_datetime" : 3, 
               "full_scan_datetime"  : 4, 
               "css_selector" : 5,
}

MAX_COLUMN = len(CSV_COLUMN)

def read_csv_with_padding(file_path, max_column):
    """
    Read a CSV file and pad missing columns with None values.

    Args:
        file_path (str): Path to the CSV file.
        num_columns (int): Number of columns expected in the CSV file.

    Returns:
        pandas.DataFrame: DataFrame containing the CSV data with padded columns.
    """
    try:
        # CSVファイルを読み込む
        df = pd.read_csv(file_path, header=None, encoding='utf-8')
        
        # カラム数がnum_columnsに足りない場合、補完する
        if len(df.columns) < max_column:
            log_print.debug("column is too short and add column")

            padding_needed = max_column - len(df.columns)
            padding = [[ 0 ] * padding_needed for _ in range(len(df))]
            df = pd.concat([df, pd.DataFrame(padding, columns=range(len(df.columns), max_column))], axis=1)
        
        # URLカラムからエンコーディングされた文字列を削除する
        df[CSV_COLUMN["url"]] = df[CSV_COLUMN["url"]].apply(lambda x: unicodedata.normalize('NFKD', x) if isinstance(x, str) else x)

        # dateframeの値に欠損値（NaN)を""に置換
        df = df.fillna("").astype(str)

        return df
    except pd.errors.EmptyDataError:
        print("指定されたファイルが空です。空ファイル内に空のデータを追加します。")
        empty_data = [[ 0 ] * max_column]
        pd.DataFrame(empty_data).to_csv(file_path, index=False, header=False)  # 空ファイル内に空のデータを追加
        return pd.DataFrame(empty_data)

def write_csv_updateDate( path : str, csv_df : pd.DataFrame):
    csv_df.iloc[:, CSV_COLUMN["run_code"]] = get_Strdatetime()

    csv_df.to_csv( path, index=False, header=False)

def write_csv_updateValues( content_hashTxt :str ,
                            csv_df : pd.DataFrame,
                            index_num : int,
                            css_selector : str) -> None:
    csv_df.at[index_num , CL_UPDATED_DATETIME] = get_Strdatetime()
    csv_df.at[index_num , CL_RESULT_VL ] = content_hashTxt
    csv_df.at[index_num , CL_CSS_SELECTOR ] = css_selector
    log_print.info(f" ## update ## - index : {index_num} - {content_hashTxt}")


# csv function end ---------------------------------------------------------------- 

def scraping_mainditect(url : str) :
    try:
        log_print.debug(f"scraping {url} is {type(url)}")
        rescored_candidate = asyncio.run(playwright_mainditect.test_main(url))

        return rescored_candidate
    except Exception as e:
        log_print.warning(f"{e}")

def choice_content(url : str, css_selector : str):
    try:
        rescored_candidate = asyncio.run(playwright_mainditect.choice_content(url,css_selector))
        return rescored_candidate
    except Exception as e:
        log_print.warning(f"{e}")

"""
def pre_proc():
    find_or_create(SAVE_CSV_DIR_PATH)

    csv_df = read_csv_with_padding(SAVE_CSV_DIR_PATH, MAX_COLUMN)

    print(csv_df)
    
    url_columnLst = csv_df.iloc[:, CL_URL].tolist()
    # print(url_columnLst)
    # print(csv_df.at[0 , 2] ,type(csv_df.at[0 , 2] ))
    return csv_df, url_columnLst
"""

# Worker function to process a single URL
def process_url(url, index_num, csv_df, error_list):
    try:
        log_print.info(f"Processing URL: {url}, index: {index_num}")
        now_sec = datetime.now()
        
        css_selector = csv_df.at[index_num, CSV_COLUMN["css_selector"]]
        run_code_time = csv_df.at[index_num, CSV_COLUMN["run_code"]]
        full_scan_datetime = csv_df.at[index_num, CSV_COLUMN["full_scan_datetime"]]
        
        diff_days = (safe_parse_datetime(run_code_time) - safe_parse_datetime(full_scan_datetime)).days
        
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
            rescored_candidate = scraping_mainditect(url)
            if rescored_candidate:
                content_hash_text = hashlib.sha256(str(rescored_candidate["links"]).encode()).hexdigest()
                csv_df.at[index_num, CSV_COLUMN["full_scan_datetime"]] = get_Strdatetime()
                update_flg = True
                result_flg = True
            else:
                log_print.info("Full scan returned None")
                error_list.append([url, "Full scan returned None"])
                return
        else:
            try:
                rescored_candidate = choice_content(url, css_selector)
                proc_time = datetime.now() - now_sec
                if proc_time.total_seconds() > PROC_MPL_SEC:
                    error_list.append([url, f"Processing time exceeded {PROC_MPL_SEC} sec -> {proc_time.total_seconds()} sec"])
                update_flg = True
            except Exception as e:
                log_print.error(e)
                return

        if rescored_candidate:
            content_hash_text = hashlib.sha256(str(rescored_candidate["links"]).encode()).hexdigest()
            if csv_df.at[index_num, CSV_COLUMN["result_vl"]] != content_hash_text:
                log_print.info(f"Updating {url} - {content_hash_text}")
                save_json(rescored_candidate, url)
                write_csv_updateValues(content_hash_text, csv_df, index_num, css_selector)
                result_flg = True
        else:
            log_print.error("Choice content is None")
            error_list.append([url, "Choice content None"])
            csv_df.at[index_num, CSV_COLUMN["full_scan_datetime"]] = ""
    except Exception as e:
        log_print.error(f"Error processing URL {url}: {e}")
        error_list.append([url, e])
    
    return result_flg, update_flg


def worker(q, csv_df, error_list):
    while True:
        try:
            url = q.get(timeout=10)
        except queue.Empty:
            log_print.info("Queue is empty, exiting worker")
            break
        
        index_num = url_column_list.index(url)
        if url is None:
            break

        result_flg, update_flg = process_url(url, index_num, csv_df, error_list)
        log_print.debug(f"Worker flags - Result: {result_flg}, Update: {update_flg}")
        q.task_done()


def initialize_queue(csv_df):
    q = queue.Queue()
    for _, row in csv_df.iterrows():
        if row[CL_URL]:
            q.put(row[CL_URL])
    return 

def start_workers(q, csv_df, error_list):
    threads = []
    for _ in range(WORKER_THREADS_NUM):
        thread = threading.Thread(target=worker, args=(q, csv_df, error_list))
        thread.daemon = True
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()


def main():
    if os.path.isdir("temp"):
        shutil.rmtree("temp")
    
    user = User("jav")
    util_str.util_handle_path(user.csv_file_path)
    
    error_list = []
    csv_df = read_csv_with_padding(user.csv_file_path, MAX_COLUMN)
    bef_df = csv_df.copy()
    global url_column_list
    url_column_list = csv_df.iloc[:, CL_URL].tolist()
    
    q = initialize_queue(csv_df)
    start_workers(q, csv_df, error_list)
    
    write_csv_updateDate(user.csv_file_path, csv_df)
    diff_urls = csv_df[csv_df.iloc[:, CL_RESULT_VL] != bef_df.iloc[:, CL_RESULT_VL]][CL_URL].tolist()
    log_print.info(diff_urls)

    file_list = asyncio.run(playwright_mainditect.save_screenshot(diff_urls, save_dir="temp"))
    
    if error_list:
        log_print.info("-------- ERROR list output -----------")
        for error_msg in error_list:
            log_print.info(error_msg)
    
    if diff_urls:
        body = text_struct.generate_html(diff_urls, file_list)
        user.send_resultmail(body, body_type="html", image_list=file_list)
    
    shutil.rmtree("temp")

if __name__ == "__main__":
    main()

 