import re
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

from dom_treeSt import DOMTreeSt

@dataclass(frozen=True)
class WebType(Enum):
    plane = "plane"
    page_changer = "page_changer"

class PageMonitor:
    def __init__(self, 
                 base_url : str, 
                 node : DOMTreeSt
                 ):
        self.base_url = base_url  # 監視対象のURL（既存の探索URL）
        self.node = node  # 解析対象のDOM情報

    def should_check_update(self):
        """ページ更新チェックを実行すべきか判定"""
        for link in self.node.links:
            if re.search(r"page[-=]\d+", link):
                return True  # ページ番号を含むリンクがあれば更新チェックが必要
        return False  # 該当リンクなし → 更新不要

    def determine_watch_page(self):
        """最新ページのURLを取得"""
        page_numbers = []
        page_format = None  # "page-" or "page=" の形式を保持
        for link in self.node.links:
            match = re.search(r"(page[-=/]?)(\d+)", link)
            if match:
                page_numbers.append(int(match.group(2)))
                if page_format is None:
                    page_format = match.group(1)  # "page-", "page=", "page/" を決定

        if not page_numbers or page_format is None:
            return None  # ページ番号が取得できない場合は None を返す

        latest_page = max(page_numbers)  # 最大ページ番号を取得

        # ベースURLのドメイン部分を取得
        parsed_url = urlparse(self.base_url)
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path.rsplit('/', 1)[0]}/"

        # 新しいURLを作成
        return f"{domain}{page_format}{latest_page}"

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
                 node : DOMTreeSt
                 ):
        self.pagemon = PageMonitor(base_url,node)
        self.node = node
        self.next_url = None

        

    def webtype_chk(self) -> Optional[str]:
        ret = self.pagemon.get_watch_url()
        if ret :
            self.node.web_type = WebType.page_changer
            self.next_url = ret
            return WebType.page_changer
        
        return WebType.plane

def test_page_monitor_1():
    """PageMonitor の単体テスト１"""
    # サンプルデータ
    base_url = "http://sample.com/def/page-1"
    node_data = DOMTreeSt(
        links = [
            "http://sample.com/def/page-1",
            "http://sample.com/def/page-2",
            "http://sample.com/def/page-10"
        ]
    )
    
    monitor = PageMonitor(base_url, node_data)
    
    assert monitor.should_check_update() == True, "ページ更新チェックが正しく判定されていません"
    expected_url = "http://sample.com/def/page-10"
    assert monitor.determine_watch_page() == expected_url, f"期待されるURL {expected_url} と一致しません"
    assert monitor.get_watch_url() == expected_url, f"更新されたURL {expected_url} と一致しません"
    
    print("すべてのテストが成功しました！")

def test_page_monitor_2():
    """PageMonitor の単体テスト１"""
    # サンプルデータ
    base_url = "http://sample.com/def/page-1"
    node_data = {
        "links": [
            "http://sample.com/def/page-1",
            "http://sample.com/def/page-2",
            "http://sample.com/def/page-10"
        ]
    }
    
    monitor = PageMonitor(base_url, node_data)
    webtype = WebTypeCHK(base_url, node_data)
    assert monitor.should_check_update() == True, "ページ更新チェックが正しく判定されていません"
    expected_url = "http://sample.com/def/page-10"
    assert monitor.determine_watch_page() == expected_url, f"期待されるURL {expected_url} と一致しません"
    assert monitor.get_watch_url() == expected_url, f"更新されたURL {expected_url} と一致しません"
    
    print("すべてのテストが成功しました！")

if __name__ == "__main__":

    test_page_monitor_2()