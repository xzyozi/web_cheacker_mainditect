import re
from urllib.parse import urlparse, urljoin
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum, auto

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
        if not isinstance(enum_str, str):
            return cls.plane
        
        member_name = enum_str.split(".")[-1].strip()
        
        # getattrを使って安全にアクセスする
        return getattr(cls, member_name, cls.plane)
    

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
        ページ内のリンクから最大のページ番号を持つリンクを見つけ、絶対URLを返します。
        """
        if not PAGINATED_URL_REGEX.search(self.base_url):
            return None

        latest_page_num = -1
        latest_link = None

        # ページリンクから最新のページ番号と対応するリンクを見つける
        for link in self.node.links:
            match = PAGE_NUMBER_CAPTURE_REGEX.search(link)
            if match:
                page_num = int(match.group(2))
                if page_num > latest_page_num:
                    latest_page_num = page_num
                    latest_link = link
        
        # ページネーションリンクが見つからなければ何もしない
        if latest_link is None:
            return None

        # ベースURLから現在のページ番号を取得
        base_match = PAGE_NUMBER_CAPTURE_REGEX.search(self.base_url)
        current_page_num = int(base_match.group(2)) if base_match else -1
        
        # 最新ページ番号が現在のページ番号より大きい場合のみURLを更新
        if latest_page_num > current_page_num:
            # `urljoin` を使って相対リンクを絶対URLに正しく解決する
            new_url = urljoin(self.base_url, latest_link)
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


