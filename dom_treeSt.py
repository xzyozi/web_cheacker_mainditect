from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height
        }


@dataclass
class DOMTreeSt:
    tag: str = ""
    id: str = ""
    attributes: Dict[str, str] = None
    children: List["DOMTreeSt"] = field(default_factory=list)
    rect: BoundingBox = field(default_factory=lambda: BoundingBox(0, 0, 0, 0))
    depth: int = 0
    text: str = ""
    score: int = 0
    css_selector: str = ""
    links: List[str] = field(default_factory=list)
    chk_url: str = ""

    def add_child(self, child: "DOMTreeSt") -> None:
        """子ノードを追加する"""
        self.children.append(child)

    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        return {
            "tag": self.tag,
            "id": self.id,
            "attributes": self.attributes,
            "children": [child.to_dict() for child in self.children],
            "rect": {
                "x": self.rect.x,
                "y": self.rect.y,
                "width": self.rect.width,
                "height": self.rect.height,
            },
            "depth": self.depth,
            "text": self.text,
            "score": self.score,
            "css_selector": self.css_selector,
            "links": self.links,
            "chk_url":self.chk_url,
        }
    
    def print_children(self) -> str:
        """子要素の出力"""
        infos = []
        for child in self.children:
            info = [
                f" child : ",
                f"    Score: {child.score}",
                f"    Rect: {child.rect}",
                f"    Depth: {child.depth}",
                f"    CSS Selector: {child.css_selector}",
            ]
            infos.append("\n".join(info) + "\n" + "-" * 60)
        
        return "\n".join(infos)

    def __repr__(self) -> str:
        """ノードの情報を見やすく表示"""
        info = [
            f"",
            f"Tag: {self.tag}",
            f"Score: {self.score}",
            f"ID: {self.id}" if self.id else "ID: None",
            f"Attributes: {self.attributes}" if self.attributes else "Attributes: None",
            f"Rect: {self.rect}",
            f"Depth: {self.depth}",
            f"CSS Selector: {self.css_selector}",
            f"Links: {', '.join(self.links)}" if self.links else "No links found"
        ]
        return "\n".join(info) + "\n" + "-" * 60