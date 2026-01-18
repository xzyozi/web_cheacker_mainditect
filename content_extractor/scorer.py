import math
from typing import Dict, List, Any, Union , Optional
from scipy import stats

from .dom_treeSt import DOMTreeSt, BoundingBox

class MainContentScorer:
    """
    DOMツリーを受け取り、各ノードがメインコンテンツである可能性をスコアリングします。
    スコアリングは以下の2段階で行われます。
    1. `find_candidates`: 全ノードを対象に、メインコンテンツ候補を大まかに絞り込むためのスコアリング。
    2. `score_parent_and_children`: 絞り込まれた候補の周辺で、より詳細なスコアリング。
    """

    # --- Scoring Parameters ---
    # スコアリングに使用する確率分布や重みを定義します。
    # これらを調整することで、どのような特徴を持つ要素を重視するかを変更できます。

    # 位置とサイズの分布: 画面中央・上部にある、横幅が広い要素を高く評価する設定
    X_DIST = stats.norm(0.5, 0.35)
    Y_DIST = stats.norm(0.5, 0.35)
    WIDTH_DIST = stats.gamma(6.7, scale=0.11)

    class Weights:
        """スコア計算における各要素の重み"""
        X = 1                   # X座標の中心度
        Y = 1                   # Y座標の上部度
        WIDTH = 1               # 幅の広さ
        HEIGHT = 1.5            # 高さ（特に重視）
        MAIN_TAG_BONUS = 0.5    # <main>タグなどへのボーナス
        MAX_NORMALIZED_HEIGHT = 0.9 # 画面からはみ出す要素へのペナルティ閾値
        LINK_LENGTH_WEIGHT = 1.0 # リンク密度の影響度
        TEXT_LENGTH_WEIGHT = 1.5 # テキスト量の影響度（特に重視）

    class LinkScoring:
        """リンク数のスコアリングパラメータ"""
        MEAN = 6      # リンク数がこの値に近いほど高評価
        STD_LOW = 5   # 平均より少ない場合のばらつき
        STD_HIGH = 30 # 平均より多い場合のばらつき

    class TextScoring:
        """テキスト量のスコアリングパラメータ"""
        MEAN = 50     # テキスト長がこの値に近いほど高評価
        STD_LOW = 40
        STD_HIGH = 1000

    def __init__(self,
                 tree: list[DOMTreeSt], 
                 width: int, 
                 height: int
                 ):
        if isinstance(tree, list):
            self.tree = tree
        else:
            raise TypeError("tree must be a list of dicts")
        
        self.width = width
        self.height = height

    def _calculate_screen_occupancy_multiplier(self, 
                                               occupancy_rate: float, 
                                               peak: float = 0.8, 
                                               sigma: float = 0.3
                                               ) -> float:
        """        
        画面占有率に基づいてスコアの倍率を計算する。  
        この関数はガウス関数（正規分布）を使用し、基準値（peak）を中心に  
        偏差（sigma）が大きくなるほどスコアを減衰させる。
        """
        exponent = -0.5 * ((occupancy_rate - peak) / sigma) ** 2
        return math.exp(exponent)

    def _score_link_length(self, node: DOMTreeSt) -> float:
        """
        要素内のリンク数に基づいてスコアを計算します。
        リンクが全くない、あるいは多すぎる場合にペナルティを与え、適度な場合に高評価します。
        これにより、ナビゲーションやフッターではなく、本文を抽出しやすくします。
        """
        link_length = len(node.links)
        if link_length == 0:
            score = 0.1
        elif link_length <= self.LinkScoring.MEAN:
            score = math.exp(-0.5 * ((link_length - self.LinkScoring.MEAN) / self.LinkScoring.STD_LOW) ** 2)
        else:
            score = math.exp(-0.5 * ((link_length - self.LinkScoring.MEAN) / self.LinkScoring.STD_HIGH) ** 2)

        return score ** self.Weights.LINK_LENGTH_WEIGHT

    def _score_text_length(self, node: DOMTreeSt) -> float:
        """
        要素内のテキスト量に基づいてスコアを計算します。
        テキストが全くない、あるいは非常に少ない場合にペナルティを与えます。
        適度な長さのテキストを持つ要素を本文の候補として高く評価します。
        """
        text_length = len(node.text)
        if text_length == 0: score = 0
        elif text_length <= self.TextScoring.MEAN:
            score = math.exp(-0.5 * ((text_length - self.TextScoring.MEAN) / self.TextScoring.STD_LOW) ** 2)
        else:
            score = math.exp(-0.5 * ((text_length - self.TextScoring.MEAN) / self.TextScoring.STD_HIGH) ** 2)
        return score ** self.Weights.TEXT_LENGTH_WEIGHT

    def _calculate_base_score(self, node: DOMTreeSt) -> float:
        """
        ノードの基本的な特徴（位置、サイズ、テキスト量など）からベーススコアを算出します。
        このスコアは、後続のスコアリング処理の基礎となります。
        """
        score = 1.0

        # 1. 画面占有率: 要素が画面に占める面積が大きいほど高スコア
        element_area = node.rect.width * node.rect.height
        page_area = self.width * self.height if self.width * self.height > 0 else 1
        occupancy_rate = element_area / page_area
        multiplier = self._calculate_screen_occupancy_multiplier(occupancy_rate)
        score *= multiplier

        # 2. 位置とサイズ: 画面中央・上部にある、幅広・高身長の要素を高スコア
        x = (node.rect.x + node.rect.width / 2) / self.width if self.width > 0 else 0
        y = node.rect.y / self.height if self.height > 0 else 0
        w = node.rect.width / self.width if self.width > 0 else 0
        h = node.rect.height / self.height if self.height > 0 else 0

        x_score = self.X_DIST.pdf(x) ** self.Weights.X
        y_score = self.Y_DIST.pdf(y) ** self.Weights.Y
        w_score = self.WIDTH_DIST.pdf(w) ** self.Weights.WIDTH
        h_score = min(h, self.Weights.MAX_NORMALIZED_HEIGHT) ** self.Weights.HEIGHT
        score *= x_score * y_score * w_score * h_score

        # 3. リンク密度とテキスト量: 本文らしさを評価
        link_density_score = self._score_link_length(node)
        text_score = self._score_text_length(node)

        return score * link_density_score * text_score

    def _score_for_candidacy(self, node: DOMTreeSt):
        """
        第一段階: メインコンテンツ候補を大まかに見つけるためのスコアリング。
        深さ(depth)を考慮せず、要素単体の特徴で評価します。
        """
        score = self._calculate_base_score(node)
        
        # <main>タグなど、メインコンテンツを示す明確な要素にはボーナスを与える
        if is_main_element(node):
            score += self.Weights.MAIN_TAG_BONUS
        
        node.score = score

    def _score_for_refinement(self, node: DOMTreeSt, depth_diff: int):
        """
        第二段階: 絞り込まれた候補群に対して、より詳細なスコアリング。
        ここではDOMの階層構造（深さ）を考慮に入れ、より深い階層の要素を重視します。
        """
        score = self._calculate_base_score(node)

        # 深さの重み: 深い階層にあるノードほど本文である可能性が高いとみなし、スコアを高くする
        depth_weight = calculate_depth_weight(node.depth - depth_diff)
        score *= depth_weight
        
        node.score = score

    def find_candidates(self) -> List[DOMTreeSt]:
        """
        DOMツリー全体をスキャンし、メインコンテンツの候補となりうる要素をリストアップします。
        `_score_for_candidacy` を用いて、大まかなスコアリングを行います。
        返り値はスコアの高い順にソートされた候補ノードのリストです。
        """
        if not self.tree:
            return []
        
        nodes = self.tree
        candidates = []
        while nodes :
            node = nodes.pop(0)

            if is_valid_element(node):
                candidates.append(node)

            self._score_for_candidacy(node)
            
            nodes.extend(node.children)

        candidates.sort(key=lambda x: x.score, reverse=True)
        
        return candidates
    
    def score_parent_and_children(self) -> list[DOMTreeSt]:
        """
        候補リスト（またはその親）とその子孫に対して、深さ(depth)を考慮した
        詳細なスコアリング(`_score_for_refinement`)を行います。
        これにより、最終的なメインコンテンツを特定します。
        """
        if not self.tree:
            return []
        
        # ツリーの最上位の深さを基準(0)とするための差分
        depth_diff = self.tree[0].depth
        
        scored_nodes : List[DOMTreeSt] = []
        for node in self.tree:
            self._score_for_refinement(node, depth_diff=depth_diff)
            scored_nodes.append(node) 

        scored_nodes.sort(key=lambda x: x.score, reverse=True)

        return scored_nodes
    
def calculate_depth_weight(current_depth : int , 
                           max_depth : int = 5,
                           base_weight :float =1.0 , 
                           weight_factor :float =4.0) -> float:
    """
    現在の階層レベルに基づいて depth の重みを計算する関数。
    深い階層にあるほど高い重みを返します。
    """
    depth_ratio = current_depth / max_depth
    weight = base_weight * (weight_factor ** depth_ratio)
    return weight

def is_main_element(node: DOMTreeSt) -> bool:
    """
    ノードが<main>タグか、idに"main"を含むなど、
    メインコンテンツであることを示す明確なヒントを持つかを判定します。
    """
    tag = node.tag.upper()
    if tag == "MAIN":
        return True
    if "id" in node.attributes and "main" in node.attributes["id"].lower():
        return True
    return False

"""
リファクタリング前の is_valid_element 関数 (参考)

def is_valid_element(node: DOMTreeSt) -> bool:
    tag = node.tag.upper()
    invalid_tags = [
        "NAV", "ASIDE", "HEADER", "FOOTER", "H1", "H2", "H3", "H4",
        "H5", "H6", "P", "BLOCKQUOTE", "PRE", "A", "THEAD", "TFOOT",
        "TH", "DD", "DT", "MENU", "BODY", "HTML",
    ]
    if tag in invalid_tags:
        return False
    
    area = node.rect.width * node.rect.height
    if area < 0.05:
        return False
    return True
"""
def is_valid_element(node: DOMTreeSt) -> bool:
    """
    ノードがメインコンテンツの候補として有効かどうかを判定します。
    明らかに本文ではない要素（ヘッダー、フッターなど）や、小さすぎる要素を除外します。
    """
    tag = node.tag.upper()
    
    # リファクタリングにより、コンテナ要素(div, sectionなど)を主に候補とするため、
    # テキスト要素(P, Hxなど)を直接の候補から除外するアプローチから、
    # 非コンテナ要素を明示的に除外するアプローチに変更。
    # 現在は、主要な非コンテンツ領域タグのみを除外対象とする。
    invalid_tags = [
        "NAV",      # ナビゲーション
        "ASIDE",    # サイドバー
        "HEADER",   # ヘッダー
        "FOOTER",   # フッター
        "MENU",     # メニュー
        "BODY",     # body全体を候補にしない
        "HTML",     # html全体を候補にしない
    ]
    if tag in invalid_tags:
        return False
    
    # 画面に対して極端に小さい要素は除外
    area = node.rect.width * node.rect.height
    if area < 0.05:
        return False
    return True
