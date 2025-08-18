import asyncio
from playwright.async_api import async_playwright, Browser
from typing import List, Dict, Optional
from content_extractor import extract_main_content
from setup_logger import setup_logger

logger = setup_logger("search_validator")

async def search_on_google(browser: Browser, keyword: str) -> List[str]:
    """
    Googleでキーワードを検索し、検索結果のURLリストを返します。
    """
    page = await browser.new_page()
    try:
        logger.info(f"Searching for '{keyword}' on Google...")
        await page.goto("https://www.google.com")
        # "q"というname属性を持つテキストエリアを探して入力
        await page.locator('textarea[name="q"]').fill(keyword)
        await page.locator('textarea[name="q"]').press("Enter")
        
        logger.info("Waiting for search results to load...")
        await page.wait_for_load_state("domcontentloaded")
        
        # 検索結果のリンクを取得 (セレクタはGoogleの仕様変更で変わりうる点に注意)
        # 'div.g' は各検索結果のコンテナを指すことが多い
        link_locators = page.locator('div.g a[href^="http"]')
        
        urls = []
        for i in range(await link_locators.count()):
            href = await link_locators.nth(i).get_attribute("href")
            if href:
                urls.append(href)

        # 重複を除外して返す
        unique_urls = list(dict.fromkeys(urls))
        logger.info(f"Found {len(unique_urls)} unique URLs.")
        return unique_urls
    except Exception as e:
        logger.error(f"Failed to search on Google: {e}")
        return []
    finally:
        await page.close()

async def main(search_keyword: str):
    """
    メイン処理: 検索、コンテンツ抽出、妥当性検証を行います。
    """
    valid_pages = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # headless=Falseにすると動作が見えます

        # 1. Googleで検索してURLリストを取得
        search_result_urls = await search_on_google(browser, search_keyword)

        if not search_result_urls:
            logger.warning("No search results found. Exiting.")
            await browser.close()
            return

        # 2. 各URLを分析
        for url in search_result_urls[:5]:  # 上位5件を対象にする例
            logger.info(f"Analyzing URL: {url}")
            try:
                # 3. リファクタリングした関数でメインコンテンツを抽出
                content_node = await extract_main_content(url, browser)

                if content_node and content_node.text:
                    # 4. 妥当性チェック (コンテンツ内にキーワードが含まれるか)
                    if search_keyword.lower() in content_node.text.lower():
                        logger.info(f"  -> VALID: Keyword found in main content.")
                        valid_pages.append({"url": url, "title": content_node.tag, "text_snippet": content_node.text[:100]})
                        # ここでショートカット生成などのアクションを呼び出す
                        # create_shortcut(url, content_node.tag)
                    else:
                        logger.warning(f"  -> INVALID: Keyword not found in main content.")
                else:
                    logger.warning(f"  -> Could not extract content from {url}")
            except Exception as e:
                logger.error(f"  -> Failed to process {url}: {e}")

        await browser.close()

    # 5. 最終結果の表示
    logger.info("\n--- Validation Complete ---")
    if valid_pages:
        logger.info("Found valid pages:")
        for page_info in valid_pages:
            logger.info(f"  - URL: {page_info['url']}")
    else:
        logger.info("No valid pages were found.")

if __name__ == "__main__":
    # ここに検索したい一意性の高い文字列（ユーザー名など）を指定します
    KEYWORD_TO_SEARCH = "playwright" 
    asyncio.run(main(KEYWORD_TO_SEARCH))
