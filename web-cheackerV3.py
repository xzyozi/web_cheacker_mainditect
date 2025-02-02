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

import util_str

# +----------------------------------------------------------------
# + my module imports
# +----------------------------------------------------------------
import playwright_mainditect_v3 as playwright_mainditect
from mail import send_email
from text_struct import text_struct

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

MAX_COLUMN = 6 

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

DEFAULT_DATETIME = "19700101 00:00"
PROC_MPL_SEC = 30
TEST_CHK= 0

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


def worker(q : queue.Queue, csv_df : pd.DataFrame, error_list : list):
    """
    Worker function to process URLs from the queue.

    Args:
        q (queue.Queue): Queue containing URLs to process.
        csv_df         : pandas dateframe class 
    """
    try :
        while True:
            try:
                url = q.get(timeout=10)  # Wait up to 10 seconds to get an item from the queue
            except queue.Empty:
                log_print.info("Queue is empty, exiting worker")
                break

            index_num = url_column_list.index(url)  # Get the index of the URL in the list
            if url is None:
                break
            
            result_flg = False
            update_flg = False
            
            log_print.info(f"Processing URL: {url } , index: {index_num}")
            
            # last_modified = get_last_modified(url)
            # if last_modified:
            #     if csv_df.at[index_num, CL_RESULT_VL] != last_modified or csv_df.at[index_num, CL_RESULT_VL] is None:
            #         log_print.info(f"{csv_df.at[index_num, CL_RESULT_VL]} is not {last_modified}) ")
            #         write_csv_updateValues(last_modified, csv_df, index_num)
            #         log_print.info(f"Updated URL for modified : {url}")
            #         result_flg = True
            now_sec = datetime.now()
            
            if result_flg == False:
                css_selector = csv_df.at[index_num, CSV_COLUMN["css_selector"]]
                run_codeTime = csv_df.at[index_num, CSV_COLUMN["run_code"]]
                full_scan_dateTime   = csv_df.at[index_num, CSV_COLUMN["full_scan_datetime"]]

                log_print.info(f'{url} - {index_num} - {css_selector}')

                log_print.debug(f"{url} - {index_num} - {run_codeTime}:{type(run_codeTime)}")
                log_print.debug(f"{url} - {index_num} - {full_scan_dateTime}: {type(full_scan_dateTime)}")

                diff_datetime = safe_parse_datetime(run_codeTime) - safe_parse_datetime(full_scan_dateTime )

                log_print.info(f"day {diff_datetime.days} days - {type(diff_datetime.days)} ")

                if not css_selector or diff_datetime.days >= 4 :
                    # full scan 
                    rescored_candidate = scraping_mainditect(url)
                    if rescored_candidate:
                        log_print.debug(rescored_candidate)
                        
                        content_hash_text = hashlib.sha256(str(rescored_candidate["links"]).encode()).hexdigest()
                        css_selector = rescored_candidate["css_selector"]
                        

                        # full scan datetime update 
                        csv_df.at[index_num , CSV_COLUMN["full_scan_datetime"]] = get_Strdatetime()

                        update_flg = True
                        log_print.info(f'{url} - {index_num} - {rescored_candidate["links"]} --- {content_hash_text}')
                        log_print.debug(f'{url} - {index_num} - {content_hash_text}')

                    else:
                        log_print.info(f"rescored_candidate is None type ")
                        error_list.append([url, "full scann None"])
                        q.task_done()
                # css selector         
                else:
                    try : 
                        rescored_candidate = choice_content(url,css_selector)
                        proc_time = datetime.now() - now_sec
                        if proc_time.total_seconds() > PROC_MPL_SEC :
                            error_list.append([url, f"processing {PROC_MPL_SEC} sec over -> {proc_time.total_seconds()} seconds"])

                    except Exception as e : log_print.error(e)

                    if rescored_candidate:
                        content_hash_text = hashlib.sha256(str(rescored_candidate["links"]).encode()).hexdigest()
                        update_flg = True
                    else:
                        log_print.error(f"choice_content is None type ")
                        error_list.append([url," choise content None"])
                        csv_df.at[index_num, CSV_COLUMN["full_scan_datetime"] ] = ""
                        q.task_done()
                        

                # Different elements
                if (csv_df.at[index_num, CSV_COLUMN["result_vl"]] != content_hash_text and update_flg ):
                    
                    log_print.info(f' update --- before {csv_df.at[index_num, CSV_COLUMN["result_vl"] ]} : after {content_hash_text} ')
                    save_json(rescored_candidate, url)
                    write_csv_updateValues(content_hash_text, csv_df, index_num, css_selector)
    except Exception as e:
        log_print.error(f"Error processing URL {url}: {e}")
        error_list.append([url, e])
    finally:
        # Ensure the task is marked as done whether successful or failed
        q.task_done()
        

def main():
    """
    Main function to run the web scraping process.
    """
#    if sys.argv[1] : user = User(sys.srgv)
#  else : 
    if os.path.isdir("temp"):
        shutil.rmtree("temp")
    user = User("jav")

    util_str.util_handle_path(user.csv_file_path)

    # use worker
    global url_column_list
    error_list = []

    csv_df = read_csv_with_padding(user.csv_file_path, MAX_COLUMN)
    log_print.info(csv_df)
    # for diff check 
    bef_df = read_csv_with_padding(user.csv_file_path, MAX_COLUMN)

    log_print.debug(csv_df.dtypes)    

    url_column_list = csv_df.iloc[:, CL_URL].tolist()

    # Create a queue and fill it with URLs
    q_pool = queue.Queue()

    for _, row in csv_df.iterrows():
        url = row[CL_URL]
        if url:
            log_print.debug(url)

            q_pool.put(url)

    # Start worker threads
    threads  = []
    for _ in range(WORKER_THREADS_NUM):
        thread = threading.Thread(target=worker, args=(q_pool, csv_df, error_list) )
        thread.daemon = True
        thread.start()
        threads.append(thread)

    # Block until all tasks are done
    # q_pool.join()

    for thread in threads:
        thread.join()

    # Update CSV file with the latest data
    write_csv_updateDate(user.csv_file_path, csv_df)
    log_print.info(csv_df)

    # diff chack of dataflame
    diff_column = csv_df.iloc[:, CL_RESULT_VL] != bef_df.iloc[:, CL_RESULT_VL]

    result = csv_df[diff_column]
    # log_print.info(result)

    diff_urls = [row[CL_URL] for row in result.values.tolist()]
    log_print.info(diff_urls)

    file_list = asyncio.run(playwright_mainditect.save_screenshot(diff_urls,save_dir="temp"))

    if len(error_list) > 0:
        log_print.info("-------- ERROR list output -----------")
        for error_msg in error_list:
            log_print.info(error_msg)

    if len(diff_urls) >= 1 :
        body = text_struct.generate_html(diff_urls,file_list)
    
        user.send_resultmail(body,body_type="html",image_list=file_list)

    shutil.rmtree("temp")

if __name__ == "__main__":
    main()

 