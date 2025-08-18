import os
import hashlib
from urllib.parse import urlparse
from PIL import Image, ImageDraw
from playwright.async_api import async_playwright

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


async def save_screenshot(url_list: list, 
                          save_dir="temp", 
                          width=500, 
                          height : int | None =None
                          ) -> list:
    """
    URLリストを受け取り、各ページのスクリーンショットを指定されたサイズで保存します。

    Args:
        url_list (list): スクリーンショットを撮るURLのリスト。
        save_dir (str, optional): 画像を保存するディレクトリ。デフォルトは "temp"。
        width (int, optional): リサイズ後の画像の幅。デフォルトは 500。
        height (int | None, optional): リサイズ後の画像の高さ。Noneの場合はアスペクト比を維持します。デフォルトは None。

    Returns:
        list: 正常に保存されたファイルのパスのリスト。
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        filelist = []
        os.makedirs(save_dir, exist_ok=True)  # フォルダがなければ作成

        for url in url_list[:]:
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                logger.warning(f"無効なURLのためスキップ: {url}")
                continue

            filename = generate_filename(url)
            filepath = os.path.join(save_dir, filename)

            try:
                await page.goto(url, wait_until='load', timeout=50000)
                await page.screenshot(path=filepath, full_page=True)

                with Image.open(filepath) as img:
                    aspect_ratio = img.height / img.width
                    new_height = height if height else int(width * aspect_ratio)
                    resized_img = img.resize((width, new_height))
                    resized_img.save(filepath)

                filelist.append(filepath)
            except Exception as e:
                logger.error(f"{url} の処理に失敗: {e}")
                url_list.remove(url)

        await browser.close()
    return filelist

def generate_filename(url: str) -> str:
    """URL から一意なファイル名を生成"""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.replace(".", "_")
    path = parsed_url.path.rstrip("/")
    last_part = path.rsplit("/", 1)[-1] if "/" in path else "index"
    return f"{domain}_{last_part}.png"
