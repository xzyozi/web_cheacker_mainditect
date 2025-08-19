import os
from PIL import Image, ImageDraw

from setup_logger import setup_logger
logger = setup_logger(__name__)

# スクリーンショットを撮り、対象要素に色味をつける
def highlight_main_content(driver, main_content, filename):
    """
    スクリーンショットを撮影し、指定されたメインコンテンツの領域をハイライトします。
    (注: この関数はSelenium WebDriverを想定しています)

    Args:
        driver: Selenium WebDriverのインスタンス。
        main_content (dict): 'rect'キーを含むメインコンテンツの辞書。
        filename (str): 保存するスクリーンショットのファイル名。
    """
    # 全画面スクリーンショット
    driver.save_screenshot(filename)
    
    # スクリーンショットに色味をつける
    img = Image.open(filename)
    draw = ImageDraw.Draw(img)
    rect = main_content["rect"]
    
    # メインコンテンツの位置を調整
    x, y = driver.execute_script("return [window.scrollX, window.scrollY];")
    rect["x"] -= x
    rect["y"] -= y
    
    draw.rectangle(((rect["x"], rect["y"]), (rect["x"] + rect["width"], rect["y"] + rect["height"])), outline=(126, 185, 255), width=5)
    img.save(filename)
