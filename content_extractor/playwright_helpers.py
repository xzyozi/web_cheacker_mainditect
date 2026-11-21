import asyncio  # Import asyncio for sleep
import hashlib
import os
from typing import Optional
from urllib.parse import urljoin, urlparse
from weakref import WeakKeyDictionary

import aiohttp
from PIL import Image, UnidentifiedImageError
from playwright.async_api import Browser, BrowserContext, Page
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from setup_logger import setup_logger

logger = setup_logger("playwright_helpers")

# Retry and timeout settings
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
ROBOTS_FETCH_TIMEOUT_SECONDS = 10


async def _cleanup_setup_resources(page: Optional[Page], context: Optional[BrowserContext]) -> None:
    """setup_page 途中で作成したページとコンテキストを独立して解放する。"""
    resources: tuple[tuple[str, Page | BrowserContext | None], ...] = (
        ("ページ", page),
        ("コンテキスト", context),
    )
    for label, resource in resources:
        if resource is not None:
            try:
                await resource.close()
            except PlaywrightError as e:
                logger.warning(f"{label}の解放に失敗しました: {e}")


async def setup_page(url: str, browser: Browser):
    """
    指定されたURLのページを準備し、Pageオブジェクトを返します。
    ページの読み込みとネットワークの安定を待ちます。
    """
    context = None
    page = None
    try:
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=10000)
        await page.wait_for_selector("body", state="attached", timeout=10000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            logger.warning("ネットワークが15秒以内にアイドル状態になりませんでした。処理を続行します。")
        return page
    except PlaywrightTimeoutError as e:
        logger.exception(f"ページのセットアップ中にタイムアウトが発生しました: {url} - {e}")
        await _cleanup_setup_resources(page, context)
        return None
    except PlaywrightError as e:
        logger.exception(f"ページのセットアップ中にPlaywrightエラーが発生: {url} - {e}")
        await _cleanup_setup_resources(page, context)
        return None
    except Exception:
        logger.exception(f"ページのセットアップ中に予期せぬエラーが発生: {url}")
        await _cleanup_setup_resources(page, context)
        raise


# セレクタが一意でないときに、目的の要素（位置が一致するもの）から、
# 親をたどる `nth-of-type` 付きの絶対パスを作る JavaScript。
# 引数: { selector, rect: {x, y, width, height} }（make_tree の bounding_box と同じビューポート相対座標）
# 戻り値: { count: ヒット件数, path: 位置が一致した要素の絶対パス（見つからなければ null） }
_UNIQUE_SELECTOR_JS = """
({ selector, rect }) => {
    let nodes;
    try {
        nodes = Array.from(document.querySelectorAll(selector));
    } catch (e) {
        return { count: -1, path: null };
    }
    const near = (a, b) => Math.abs(a - b) < 1;
    const target = nodes.find((el) => {
        const r = el.getBoundingClientRect();
        return near(r.x, rect.x) && near(r.y, rect.y)
            && near(r.width, rect.width) && near(r.height, rect.height);
    });
    if (!target) {
        return { count: nodes.length, path: null };
    }
    const parts = [];
    for (let el = target; el && el.nodeType === 1; el = el.parentElement) {
        const tag = el.tagName.toLowerCase();
        if (tag === 'html') { parts.unshift('html'); break; }
        let index = 1;
        for (let s = el.previousElementSibling; s; s = s.previousElementSibling) {
            if (s.tagName === el.tagName) index += 1;
        }
        parts.unshift(`${tag}:nth-of-type(${index})`);
    }
    return { count: nodes.length, path: parts.join(' > ') };
}
"""


async def ensure_unique_selector(page: Page, selector: str, rect: dict) -> str:
    """セレクタがページ内で1件だけにヒットすることを確認し、複数ヒットなら一意なセレクタに置き換える。

    同じクラスの要素が複数あると、保存したセレクタが次回に別の要素を指して、誤検知の原因になる。
    複数ヒットしたときは、位置（`rect`）が一致する要素から `nth-of-type` 付きの絶対パスを作る。
    確認できなかった場合（無効なセレクタ・位置が一致する要素が無い）は、元のセレクタを返す。
    `make_tree` が取得した `bounding_box` と比較するため、同じスクロール位置で呼び出すことを前提とする。

    Args:
        page: 対象ページ。
        selector: 確認するセレクタ。
        rect: 目的の要素の位置とサイズ（ビューポート相対座標）。`x`, `y`, `width`, `height`。
    """
    if not selector:
        return selector
    try:
        result = await page.evaluate(_UNIQUE_SELECTOR_JS, {"selector": selector, "rect": rect})
    except PlaywrightError as e:
        logger.warning(f"セレクタの一意性を確認できませんでした: {selector} - {e}")
        return selector

    if not isinstance(result, dict):
        logger.warning(f"セレクタの一意性の確認結果が不正です: {selector}")
        return selector

    count = result.get("count", 0)
    path = result.get("path")
    if not isinstance(count, int):
        return selector
    if count == 1:
        return selector
    if count > 1 and path:
        logger.info(f"セレクタが{count}件にヒットするため、一意なパスに置き換えます: {selector} -> {path}")
        return str(path)
    logger.warning(f"セレクタを一意にできませんでした（ヒット{count}件）: {selector}")
    return selector


async def close_page(page: Page) -> None:
    """`setup_page` が作成したページと、そのブラウザコンテキストを閉じる。

    `page.close()` だけではコンテキストが残り続け、URL数に比例してメモリを消費するため、
    ページを閉じた後にコンテキストも閉じる。閉じる処理の失敗は、後続のURL処理を止めないよう記録のみとする。
    """
    await _cleanup_setup_resources(page, page.context)


async def adjust_page_view(page: Page) -> dict:
    """ページのサイズを調整し、スクロールを実行"""
    dimensions = await page.evaluate("""() => {
        return {
            width: Math.max(document.body.scrollWidth, document.body.offsetWidth,
                            document.documentElement.clientWidth, document.documentElement.scrollWidth,
                            document.documentElement.offsetWidth),
            height: Math.max(document.body.scrollHeight, document.body.offsetHeight,
                             document.documentElement.clientHeight, document.documentElement.scrollHeight,
                             document.documentElement.offsetHeight)
        }
    }""")

    await page.set_viewport_size({"width": dimensions["width"], "height": dimensions["height"]})
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(2000)

    return dimensions


async def fetch_robots_txt(url):
    """対象ウェブサイトからrobots.txtの内容を取得します。"""
    parsed_url = urlparse(url)
    robots_url = urljoin(f"{parsed_url.scheme}://{parsed_url.netloc}", "/robots.txt")
    timeout = aiohttp.ClientTimeout(total=ROBOTS_FETCH_TIMEOUT_SECONDS)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(robots_url) as response:
                if response.status == 200:
                    return await response.text()
                return None
    except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError) as e:
        logger.error(f"robots.txtの取得中にエラーが発生: {robots_url} - {e}")
        return None


def is_scraping_allowed(
    robots_txt: str,
    target_path: str,
) -> bool:
    """robots.txtの内容に基づき、指定されたパスのスクレイピングが許可されているか確認します。"""
    from io import StringIO
    from urllib.robotparser import RobotFileParser

    robot_parser = RobotFileParser()
    robot_parser.parse(StringIO(robots_txt).readlines())

    return robot_parser.can_fetch("*", target_path)


# robots.txt の取得結果をオリジン（scheme://host）ごとに保持する。
# 1回の実行で同じサイトに何度もアクセスしないよう、取得失敗（None）もキャッシュする。
_ROBOTS_CACHE: dict[str, str | None] = {}
# 同一オリジンへの並列判定で重複取得を防ぐため、イベントループごとにオリジン単位のロックを保持する。
_ROBOTS_LOCKS: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]] = WeakKeyDictionary()


def _get_robots_lock(origin: str) -> asyncio.Lock:
    """現在のイベントループに紐づくオリジン単位のロックを返す。"""
    loop = asyncio.get_running_loop()
    locks = _ROBOTS_LOCKS.setdefault(loop, {})
    lock = locks.get(origin)
    if lock is None:
        lock = asyncio.Lock()
        locks[origin] = lock
    return lock


async def is_url_allowed(url: str) -> bool:
    """robots.txt に基づき、URL へのアクセスが許可されているか判定する。

    robots.txt はオリジンごとに1回だけ取得してキャッシュする。
    robots.txt が無い・取得できない場合と、URL を解析できない場合は許可として扱う
    （後者の検証は呼び出し側の責務）。
    """
    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        return True

    origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
    if origin not in _ROBOTS_CACHE:
        async with _get_robots_lock(origin):
            if origin not in _ROBOTS_CACHE:
                _ROBOTS_CACHE[origin] = await fetch_robots_txt(url)

    robots_txt = _ROBOTS_CACHE[origin]
    if not robots_txt:
        return True

    allowed = is_scraping_allowed(robots_txt, parsed_url.path or "/")
    if not allowed:
        logger.info(f"robots.txtにより許可されていません: {url}")
    return allowed


async def save_screenshot(
    browser: Browser, url_list: list, save_dir="temp", width=500, height: Optional[int] = None
) -> list:
    """
    URLリストを受け取り、各ページのスクリーンショットを指定されたサイズで保存します。
    成功した場合はファイルパスを、失敗した場合はNoneをリストに格納して返します。
    """
    screenshot_paths: list[str | None] = []
    os.makedirs(save_dir, exist_ok=True)

    for url in url_list:
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            logger.warning(f"無効なURLのためスキップ: {url}")
            screenshot_paths.append(None)
            continue

        if not await is_url_allowed(url):
            logger.info(f"robots.txtにより許可されていないため、スクリーンショットをスキップ: {url}")
            screenshot_paths.append(None)
            continue

        filename = generate_filename(url)
        filepath = os.path.join(save_dir, filename)

        success = False
        for attempt in range(MAX_RETRIES):
            context = None
            page = None
            try:
                # 毎回新しいコンテキストとページを作成して分離を強化
                context = await browser.new_context(viewport={"width": 1920, "height": 1080})
                page = await context.new_page()

                await page.goto(url, wait_until="load", timeout=30000)
                await page.screenshot(path=filepath, full_page=True)

                with Image.open(filepath) as img:
                    aspect_ratio = img.height / img.width
                    new_height = height if height else int(width * aspect_ratio)
                    resized_img = img.resize((width, new_height))
                    resized_img.save(filepath)

                screenshot_paths.append(filepath)
                logger.info(f"スクリーンショットを保存しました: {filepath}")
                success = True
                break
            except (PlaywrightTimeoutError, OSError, PlaywrightError, UnidentifiedImageError) as e:
                if isinstance(e, (PlaywrightTimeoutError, OSError)):
                    logger.warning(
                        f"{url} のスクリーンショット処理で既知のエラー "
                        f"(試行 {attempt + 1}/{MAX_RETRIES}): {type(e).__name__} - {e}"
                    )
                else:
                    logger.exception(f"{url} のスクリーンショット処理中にエラー (試行 {attempt + 1}/{MAX_RETRIES})")

                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    logger.error(
                        f"{url} のスクリーンショット処理が最大試行回数 ({MAX_RETRIES}) を超えても成功しませんでした。"
                    )
            except Exception:
                logger.exception(f"{url} のスクリーンショット処理中に予期せぬエラーが発生しました")
                raise
            finally:
                if page:
                    await page.close()
                if context:
                    await context.close()

        if not success:
            screenshot_paths.append(None)

    return screenshot_paths


def generate_filename(url: str) -> str:
    """URL から一意なファイル名を生成"""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.replace(".", "_")
    path = parsed_url.path.rstrip("/")
    last_part = path.rsplit("/", 1)[-1] if "/" in path else "index"
    # ファイル名が長くなりすぎるのを防ぐためにハッシュを追加
    path_hash = hashlib.md5(path.encode()).hexdigest()[:8]
    return f"{domain}_{last_part}_{path_hash}.png"
