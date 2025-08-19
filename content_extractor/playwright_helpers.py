import os
import hashlib
from urllib.parse import urlparse, urljoin
import aiohttp
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError
from PIL import Image
import traceback

from setup_logger import setup_logger
logger = setup_logger("playwright_helpers")

async def setup_page(url : str, 
                     browser : Browser
                     ):
    """
    指定されたURLのページを準備し、Pageオブジェクトを返します。
    ページの読み込みとネットワークの安定を待ちます。
    """
    try:
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        await page.goto(url, wait_until='domcontentloaded', timeout=10000)
        await page.wait_for_selector('body', state='attached', timeout=10000)
        try:
            await page.wait_for_load_state('networkidle', timeout=15000)
        except PlaywrightTimeoutError:
            logger.warning("ネットワークが15秒以内にアイドル状態になりませんでした。処理を続行します。")
        return page
    except Exception as e:
        logger.error(f"ページのセットアップ中にエラーが発生: {e}")
        traceback.print_exc()
        return None

async def adjust_page_view(page: Page) -> dict:
    """ページのサイズを調整し、スクロールを実行"""
    dimensions = await page.evaluate('''() => {
        return {
            width: Math.max(document.body.scrollWidth, document.body.offsetWidth, 
                            document.documentElement.clientWidth, document.documentElement.scrollWidth, 
                            document.documentElement.offsetWidth),
            height: Math.max(document.body.scrollHeight, document.body.offsetHeight, 
                             document.documentElement.clientHeight, document.documentElement.scrollHeight, 
                             document.documentElement.offsetHeight)
        }
    }''')

    await page.set_viewport_size({"width": dimensions['width'], "height": dimensions['height']})
    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    await page.wait_for_timeout(2000)

    return dimensions

async def fetch_robots_txt(url):
    """対象ウェブサイトからrobots.txtの内容を取得します。"""
    parsed_url = urlparse(url)
    robots_url = urljoin(f"{parsed_url.scheme}://{parsed_url.netloc}", '/robots.txt')
    
    async with aiohttp.ClientSession() as session:
        async with session.get(robots_url) as response:
            if response.status == 200:
                return await response.text()
            return None

def is_scraping_allowed(robots_txt : str, 
                        target_path : str,
                        ) -> bool:
    """robots.txtの内容に基づき、指定されたパスのスクレイピングが許可されているか確認します。"""
    from urllib.robotparser import RobotFileParser
    from io import StringIO

    robot_parser = RobotFileParser()
    robot_parser.parse(StringIO(robots_txt).readlines())
    
    return robot_parser.can_fetch("*", target_path)


async def save_screenshot(url_list: list, 
                          save_dir="temp", 
                          width=500, 
                          height : int | None =None
                          ) -> list:
    """URLリストを受け取り、各ページのスクリーンショットを指定されたサイズで保存します。"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        filelist = []
        os.makedirs(save_dir, exist_ok=True)

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
    # ファイル名が長くなりすぎるのを防ぐためにハッシュを追加
    path_hash = hashlib.md5(path.encode()).hexdigest()[:8]
    return f"{domain}_{last_part}_{path_hash}.png"