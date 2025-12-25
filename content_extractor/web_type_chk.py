import re
from urllib.parse import urlparse, urljoin
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum, auto

# This import is moved inside __main__ to allow running the script directly
# from .dom_treeSt import DOMTreeSt 

# --- Regex Constants ---
# Matches 'page' followed by an optional separator (-, =, /) and digits.
# Used to identify URLs that are part of a paginated series.
PAGINATED_URL_REGEX = re.compile(r"page[-=/]?\d+")

# Matches 'page' followed by a required separator (-, =) and digits.
# Used to check for pagination links within a page.
PAGINATION_LINK_REGEX = re.compile(r"page[-=]\d+")

# Captures the page format (e.g., "page-", "page/") and the page number.
# Used to determine the latest page number from links.
PAGE_NUMBER_CAPTURE_REGEX = re.compile(r"(page[-=/]?)(\d+)")


class WebType(Enum):
    plane = ("plane", 1)
    page_changer = ("page_changer", 2)
    not_quickscan = ("not_quickscan", 3)

    def __init__(self, value: str, priority: int):
        self._value_ = value
        self._priority = priority 

    @property
    def priority(self) -> int:
        return self._priority  

    def __lt__(self, other: "WebType") -> bool:
        return self.priority < other.priority

    def __eq__(self, other: "WebType") -> bool:
        return self.priority == other.priority

    @classmethod
    def from_string(cls, enum_str: str) -> "WebType":
        if not isinstance(enum_str, str) or not enum_str:
            return cls.plane
        
        member_name = enum_str.split(".")[-1] # "WebType.plane"でも"plane"でも対応
        try:
            return cls[member_name.strip()]
        except KeyError:
            return cls.plane
    

class PageMonitor:
    def __init__(self, 
                 base_url : str, 
                 node : 'DOMTreeSt'
                 ):
        self.base_url = base_url  # 監視対象のURL（既存の探索URL）
        self.node = node  # 解析対象のDOM情報

    def should_check_update(self):
        """ページ更新チェックを実行すべきか判定"""
        if PAGINATED_URL_REGEX.search(self.base_url) :

            for link in self.node.links:
                if PAGINATION_LINK_REGEX.search(link):
                    return True  # ページ番号を含むリンクがあれば更新チェックが必要
        return False  # 該当リンクなし → 更新不要

    def determine_watch_page(self):
        """
        最新ページのURLを取得します。
        ページ内のリンクから最大のページ番号を見つけ、ベースURLのページ番号部分をそれで置換します。
        """
        page_numbers = []
        # ページリンクからページ番号を収集
        for link in self.node.links:
            match = PAGE_NUMBER_CAPTURE_REGEX.search(link)
            if match:
                page_numbers.append(int(match.group(2)))

        if not page_numbers:
            return None

        latest_page_num = max(page_numbers)

        # ベースURLにページ番号パターンがあるか確認
        base_match = PAGE_NUMBER_CAPTURE_REGEX.search(self.base_url)
        if not base_match:
            # ベースURLがページネーション形式でない場合、何もしない
            return None
            
        current_page_num = int(base_match.group(2))

        # 最新ページ番号が現在のページ番号より大きい場合のみURLを更新
        if latest_page_num > current_page_num:
            # page_format (e.g., "page-", "page/") and the number
            page_part_format = base_match.group(1)
            # Replace the page part of the base_url with the new latest page number
            new_url = self.base_url.replace(base_match.group(0), f"{page_part_format}{latest_page_num}")
            return new_url
        
        return None

    def typechk(self):
        """URLの変更を検出する"""
        new_watch_url = self.determine_watch_page()
        return new_watch_url if new_watch_url and new_watch_url != self.base_url else None

    def get_watch_url(self):
        """URLが変更されていれば新しいURLを返す"""
        return self.typechk() if self.should_check_update() else None


class WebTypeCHK() :
    def __init__(self, 
                 base_url : str, 
                 node : 'DOMTreeSt'
                 ):
        self.pagemon = PageMonitor(base_url,node)
        self.node = node
        self.next_url = None

        

    def webtype_chk(self) -> str:
        """
        Webページのタイプを文字列として返す。
        """
        # ページャー形式のリンクから新しいURLを決定しようと試みる
        new_watch_url = self.pagemon.determine_watch_page()
        
        # 新しいページが見つかり、それが現在のURLと異なる場合
        if new_watch_url and new_watch_url != self.pagemon.base_url:
            self.next_url = new_watch_url
            # webtypeはURL自体で判定するため、ここでは変更しない

        # 新しいページが見つからなくても、現在のURL自体がページャー形式の場合
        if PAGINATED_URL_REGEX.search(self.pagemon.base_url):
            return WebType.page_changer.name
            
        return WebType.plane.name

if __name__ == "__main__":
    import sys
    import os
    # Add the parent directory to the path to allow relative imports
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from content_extractor.dom_treeSt import DOMTreeSt

    # --- Test Case 1: Standard pagination, URL should be modified ---
    base_url_1 = "http://sample.com/def/page-1"
    node_data_1 = DOMTreeSt(
        links=[
            "http://sample.com/def/page-1",
            "http://sample.com/def/page-2",
            "http://sample.com/def/page-10"
        ]
    )
    monitor_1 = PageMonitor(base_url_1, node_data_1)
    expected_url_1 = "http://sample.com/def/page-10"
    actual_url_1 = monitor_1.determine_watch_page()
    assert actual_url_1 == expected_url_1, f"Test 1 Failed: Expected {expected_url_1}, Got {actual_url_1}"
    print("Test Case 1 Passed!")

    # --- Test Case 2: On the last page, should return None ---
    base_url_2 = "http://sample.com/def/page-10"
    node_data_2 = DOMTreeSt(
        links=[
            "http://sample.com/def/page-8",
            "http://sample.com/def/page-9",
            "http://sample.com/def/page-10"
        ]
    )
    monitor_2 = PageMonitor(base_url_2, node_data_2)
    expected_url_2 = None
    actual_url_2 = monitor_2.determine_watch_page()
    assert actual_url_2 == expected_url_2, f"Test 2 Failed: Expected {expected_url_2}, Got {actual_url_2}"
    print("Test Case 2 Passed!")

    # --- Test Case 3: The "page/page" bug case, URL should be modified correctly ---
    base_url_3 = "http://sample.com/articles/page/3"
    node_data_3 = DOMTreeSt(
        links=[
            "/articles/page/2",
            "/articles/page/4",
            "/articles/page/5",
        ]
    )
    monitor_3 = PageMonitor(base_url_3, node_data_3)
    expected_url_3 = "http://sample.com/articles/page/5"
    actual_url_3 = monitor_3.determine_watch_page()
    assert actual_url_3 == expected_url_3, f"Test 3 Failed: Expected {expected_url_3}, Got {actual_url_3}"
    print("Test Case 3 Passed!")

    # --- Test Case 4: WebTypeCHK integration check ---
    chk_4 = WebTypeCHK(base_url_3, node_data_3)
    web_type_4 = chk_4.webtype_chk()
    assert web_type_4 == "page_changer", f"Test 4 Failed: Expected web_type page_changer, Got {web_type_4}"
    assert chk_4.next_url == expected_url_3, f"Test 4 Failed: Expected next_url {expected_url_3}, Got {chk_4.next_url}"
    print("Test Case 4 Passed!")

    # --- Test Case 5: WebTypeCHK on last page ---
    # Even on the last page, the type should be page_changer, but next_url should be None
    chk_5 = WebTypeCHK(base_url_2, node_data_2)
    web_type_5 = chk_5.webtype_chk()
    assert web_type_5 == "page_changer", f"Test 5 Failed: Expected web_type page_changer, Got {web_type_5}"
    assert chk_5.next_url is None, f"Test 5 Failed: Expected next_url None, Got {chk_5.next_url}"
    print("Test Case 5 Passed!")

    # --- Test Case 6: Base URL is not a paginated URL ---
    base_url_6 = "http://sample.com/regular/article.html"
    node_data_6 = DOMTreeSt(
        links=["http://sample.com/page-1", "http://sample.com/page-2"]
    )
    monitor_6 = PageMonitor(base_url_6, node_data_6)
    expected_url_6 = None # Should be None because base_url doesn't match
    actual_url_6 = monitor_6.determine_watch_page()
    assert actual_url_6 == expected_url_6, f"Test 6 Failed: Expected {expected_url_6}, Got {actual_url_6}"
    chk_6 = WebTypeCHK(base_url_6, node_data_6)
    web_type_6 = chk_6.webtype_chk()
    assert web_type_6 == "plane", f"Test 6 Failed: Expected web_type plane, Got {web_type_6}"
    assert chk_6.next_url is None, f"Test 6 Failed: Expected next_url None, Got {chk_6.next_url}"
    print("Test Case 6 Passed!")

    print("\nAll tests passed successfully!")
