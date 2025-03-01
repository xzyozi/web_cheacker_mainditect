import math
from typing import Dict, List, Any, Union , Optional
from scipy import stats

from dom_treeSt import DOMTreeSt, BoundingBox

class MainContentScorer:
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

        self.init_depth_flag = True
    

    def _calculate_screen_occupancy_multiplier(self, 
                                               occupancy_rate: float, 
                                               peak: float = 0.8, 
                                               sigma: float = 0.3
                                               ) -> float:
        """        
        画面占有率に基づいてスコアの倍率を計算する。  
        この関数はガウス関数（正規分布）を使用し、基準値（peak）を中心に  
        偏差（sigma）が大きくなるほどスコアを減衰させる。

        :param occupancy_rate: The rate of screen occupancy (0 to 1).  
                    要素が画面全体に占める面積の割合（0～1の範囲）。
                    例: `0.5` → 画面の 50% を占める要素  
                        `0.1` → 画面の 10% を占める要素  

        :param peak: The peak point of the Gaussian curve (default is 0.9).  
                    スコアが最大となる画面占有率（デフォルトは `0.9` = 90%）。  
                    これより離れるほどスコアが減衰する。  
                    例: `peak=0.7` にすると 70% 占有の要素が最も高評価される。

        :param sigma: The standard deviation of the Gaussian curve (default is 0.1).  
                    正規分布の標準偏差（デフォルトは `0.1`）。  
                    `sigma` が小さいほど減衰が急になり、評価範囲が狭くなる。  
                    `sigma` が大きいと広範囲の要素が高スコアを維持する。  

        :return: The multiplier for the score.  
                スコア倍率（`1.0` が最大で、`peak` から離れるほど指数関数的に減衰する）。

        **スコアの変化の例:**
        - `peak = 0.9`, `sigma = 0.1` → **90% 占有の要素が最も評価され、それ以外は急減衰**
        - `peak = 0.7`, `sigma = 0.2` → **70% 〜 90% 占有の要素も比較的高スコアを維持**
        - `sigma` を `0.05` にすると **90% 付近以外の要素は大幅にスコアダウン**
        - `sigma` を `0.2` にすると **広い範囲（70%〜100%）の要素が評価される**
        """
        exponent = -0.5 * ((occupancy_rate - peak) / sigma) ** 2
        return math.exp(exponent)



    def _score_node(self, 
                     node: DOMTreeSt,
                     pre_mode : bool = False ,
                     depth_flag : bool = True,
                     maintag_addscore : bool = False,
                     ) -> None:
        if self.init_depth_flag :
            # 一番上のtreeを0にするために差分をとる
            self.parent_depth_diff = node.depth 
            self.init_depth_flag = False
            # print("★ top level depth")
            # print(f' parent depth diff : {self.parent_depth_diff}  , depth : {node.depth}')
            # print_content(node)

        score = 1
        """
        if pre_mode :
            if is_main_element(node) :
                score += 1
        """
        try:
            link_count = len(node.links)  # リンクの数を取得

            link_score = 0.2 * min(link_count, 5)

            score *= link_score
            
        except : 
            # print("not link")
            pass


        # Calculate the screen occupancy rate
        element_area = node.rect.width * node.rect.height
        page_area = self.width * self.height
        occupancy_rate = element_area / page_area
        multiplier = self._calculate_screen_occupancy_multiplier(occupancy_rate)
    

        score *= multiplier


        x = (node.rect.x + node.rect.width / 2) / self.width  # X座標を正規化
        if self.height != 0:
            y = node.rect.y / self.height  # Y座標を正規化
        else:
            y = 0  # heightが0の場合はyを0に設定
        w = node.rect.width / self.width  # 幅を正規化
        if self.height != 0:
            h = node.rect.height / self.height  # 高さを正規化
        else:
            h = 0  # heightが0の場合は高さを0に設定

        # 正規化された座標と寸法から、各要素のスコアを計算
        x_score = X_DIST.pdf(x) ** WeightBox.x
        y_score = Y_DIST.pdf(y) ** WeightBox.y
        w_score = WIDTH_DIST.pdf(w) ** WeightBox.width
        h_score = min(h, 0.9) ** WeightBox.height

        score *= x_score * y_score * w_score * h_score

        link_score = 1  # リンクのスコアを初期化
        """ before code 
        try:
            link_count = len(node.get("links", []))  # リンクの数を取得
            link_score *= 0.2 * min(link_count, 5)  # リンクのスコアを計算
        except:
            pass
        """
        link_count =  score_link_length(node)

        # text_score = score_text_length(node)  # テキスト量に基づくスコアを計算


        if depth_flag :
            # ネストが深いほどスコアを高く設定する
            depth_weight = calculate_depth_weight( node.depth - self.parent_depth_diff)  # 深さに基づく重みを計算
            score *= depth_weight  # スコアを計算
            # print("★  code passed to depth weight calculation " + str(depth_weight ) ) 
        
        node.score = score * link_score  # * text_score  # 総合スコアを計算


        if maintag_addscore :
            if is_main_element(node):
                node.score += 0.5



        """
        for child in node.get("children", []):  # 子要素を再帰的にスコアリング
            self._score_node(child)
        """


    def find_candidates(self) -> List[DOMTreeSt]:
        # self.tree = [self.tree] # ルートノードを List[Dict] に変換
        # if type(self.tree) == dict :
        #     nodes = [self.tree] # ルートノードを List[Dict] に変換
        # else : nodes = self.tree

        nodes = self.tree
        candidates = []
        while nodes :
            node = nodes.pop(0)

            if is_valid_element(node):
                candidates.append(node)

            self._score_node(node, pre_mode=True, depth_flag=False, maintag_addscore=True) 
            # print(f"Scored node: {node['tag']}, Score: {node['score']}, Valid: {is_valid_element(node)}")  # デバッグ用の出力
            
            nodes.extend(node.children)  # 子ノードを追加

        candidates.sort(key=lambda x: x.score, reverse=True)
        
        return candidates
    
    # scoring for children nodes
    def score_parent_and_children(self) -> list[DOMTreeSt]: 
        """
        親ノードとその子ノードのスコアを計算する

        Args:

        Returns:
            scored_nodes (list[Dict]}: 親ノードとその子ノードのスコアリング結果を含む辞書のリスト
        """
        scored_nodes : List[DOMTreeSt] = []
        # self._score_node(parent_node)  # 親ノードのスコアを計算
        # scored_nodes.append(parent_node)  # 親ノードを追加

        # for child_node in parent_node.get("children", []):
        #     self._score_node(child_node)  # 子ノードのスコアを計算
        #     scored_nodes.append(child_node)  # 子ノードを追加

        for node in self.tree:
            self._score_node(node)
            scored_nodes.append(node) 

        scored_nodes.sort(key=lambda x: x.score, reverse=True)

        return scored_nodes
    

# + ----------------------------------------------------------------
# + link count socering 
# + ----------------------------------------------------------------
LINK_LENGTH_WEIGHT = 1.0  # リンクの重みの係数
LINK_LENGTH_MEAN = 6    # 文字数の平均値
LINK_LENGTH_STD_LOW = 5     # 文字数の標準偏差
LINK_LENGTH_STD_HIGH = 30


def score_link_length(node: DOMTreeSt) -> float:
    """
    要素内のlink量に基づいてスコアを計算する関数

    Args:
        node (Dict): 要素の情報が格納された辞書

    Returns:
        float: link量に基づくスコア
    """
    link_length = len(node.links)  # 要素内のlink数を取得
    # リンクがない場合、スコアを0にするのではなく0.1にするようにする
    # if text_length == 0:score = 0
    if link_length == 0:score = 0.1
    elif link_length <= LINK_LENGTH_MEAN:
        # 平均未満の場合、低い標準偏差を使用してスコアを計算
        score = math.exp(-0.5 * ((link_length - LINK_LENGTH_MEAN) / LINK_LENGTH_STD_LOW) ** 2)
    else:
        # 平均以上の場合、高い標準偏差を使用してスコアを計算
        score = math.exp(-0.5 * ((link_length - LINK_LENGTH_MEAN) / LINK_LENGTH_STD_HIGH) ** 2)

    # スコアに重みを掛ける
    weighted_score = score ** LINK_LENGTH_WEIGHT
    
    return weighted_score

# +----------------------------------------------------------------
# + Constant definition
# +----------------------------------------------------------------

# 特徴量の分布を定義します
X_DIST = stats.norm(0.5, 0.35)   # X軸の特徴量の分布
Y_DIST = stats.norm(0.5, 0.35)  # Y軸の特徴量の分布
WIDTH_DIST = stats.gamma(6.7, scale=0.11)  # 幅の特徴量の分布

# スコアリングの重みを定義します
WEIGHTS = {
    "x": 1,        # X軸の重み
    "y": 1,        # Y軸の重み
    "width": 1,  # 幅の重み
    "height": 1.5    # 高さの重み
}

class WeightBox(BoundingBox):
    x = 1         # X軸の重み
    y = 1         # Y軸の重み
    width = 1     # 幅の重み
    height = 1.5  # 高さの重み

# テキスト量のスコアリングに関する定数
TEXT_LENGTH_WEIGHT = 1.5  # テキスト量の重みの係数
TEXT_LENGTH_MEAN = 50    # 文字数の平均値
TEXT_LENGTH_STD_LOW = 40     # 文字数の標準偏差（平均未満の場合）
TEXT_LENGTH_STD_HIGH = 1000  # 文字数の標準偏差（平均以上の場合）


def score_text_length(node: DOMTreeSt) -> float:
    """
    要素内のテキスト量に基づいてスコアを計算する関数

    Args:
        node (Dict): 要素の情報が格納された辞書

    Returns:
        float: テキスト量に基づくスコア
    """
    text_length = len(node.text)  # 要素内のテキストの文字数を取得
    # print(f'id: {node.get("id")} text: {text_length}')    

    if text_length == 0: score = 0
    elif text_length <= TEXT_LENGTH_MEAN:
        # 平均未満の場合、低い標準偏差を使用してスコアを計算
        score = math.exp(-0.5 * ((text_length - TEXT_LENGTH_MEAN) / TEXT_LENGTH_STD_LOW) ** 2)
    else:
        # 平均以上の場合、高い標準偏差を使用してスコアを計算
        score = math.exp(-0.5 * ((text_length - TEXT_LENGTH_MEAN) / TEXT_LENGTH_STD_HIGH) ** 2)

    # スコアに重みを掛ける
    weighted_score = score ** TEXT_LENGTH_WEIGHT
    
    return weighted_score


# + ----------------------------------------------------------------
# +  depth weight
# + ----------------------------------------------------------------
def calculate_depth_weight(current_depth : int , 
                           max_depth : int = 7,
                           base_weight :float =1.0 , 
                           weight_factor :float =4.0) -> float:
    """
    現在の階層レベルに基づいて depth の重みを計算する関数

    Args:
        current_depth (int): 現在の階層レベル
        max_depth (int): 最大の階層レベル (デフォルト: 8)
        base_weight (float): ベースの重み係数 (デフォルト: 1.0)
        weight_factor (float): 重み係数の増加率 (デフォルト: 4.0)

    Returns:
        float: 計算された depth の重み
    """
    # 最大深さと現在の深さの比率を計算
    depth_ratio = current_depth / max_depth

    weight = base_weight * (weight_factor ** depth_ratio)

    return weight

def is_main_element(node: DOMTreeSt) -> bool:
    """
    メインコンテンツ判定
    """

    tag = node.tag.upper()
    if tag == "MAIN":
        return True
    if "id" in node.attributes and "main" in node.attributes["id"].lower():
        return True
    return False

# def is_skippable(node: Dict) -> bool:
#     if len(node.children) != 1:
#         return False
#     child = node.children[0]
#     skip_threshold = 5
#     if (
#         abs(node.rect.x - child.rect.x) < skip_threshold
#         and abs(node.rect.y - child.rect.y) < skip_threshold
#         and abs(node.rect.width - child.rect.width) < skip_threshold
#         and abs(node.rect.height - child.rect.height) < skip_threshold
#     ):
#         return True
#     return False

def is_valid_element(node: DOMTreeSt) -> bool:
    tag = node.tag.upper()
    invalid_tags = [
        "NAV",
        "ASIDE",
        "HEADER",
        "FOOTER",
        "H1",
        "H2",
        "H3",
        "H4",
        "H5",
        "H6",
        "P",
        "BLOCKQUOTE",
        "PRE",
        "A",
        "THEAD",
        "TFOOT",
        "TH",
        "DD",
        "DT",
        "MENU",
        "BODY",
        "HTML",
    ]
    if tag in invalid_tags:
        return False
    
    area = node.rect.width * node.rect.height
    if area < 0.05:
        return False
    return True