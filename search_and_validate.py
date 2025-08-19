import asyncio
from playwright.async_api import async_playwright, Browser
from typing import List, Dict, Optional
from content_extractor import run_search_quality_evaluation_standalone
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
    # 1. Googleで検索してURLリストを取得 (この部分は変更なし)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        search_result_urls = await search_on_google(browser, search_keyword)
        await browser.close()

    if not search_result_urls:
        logger.warning("No search results found. Exiting.")
        return

    # 2. 各URLを分析 (スタンドアロン関数を呼び出す)
    for url in search_result_urls[:5]:  # 上位5件を対象にする例
        logger.info(f"Analyzing URL: {url}")
        try:
            # 3. 新しいスタンドアロン関数で品質評価を実行
            content_node = await run_search_quality_evaluation_standalone(url, search_keyword)

            if content_node and content_node.is_empty_result:
                logger.warning(f"  -> EMPTY: Page identified as 'no results' for {url}")
                # ここで空の結果ページに対する処理を行う (例: valid_pagesには追加しない)
            elif content_node and content_node.text:
                # 4. 妥当性チェック (品質カテゴリとキーワードで判断)
                logger.info(f"  -> Quality: {content_node.quality_category} (SQS: {content_node.sqs_score:.2f})")
                
                if content_node.quality_category == "Valid" and search_keyword.lower() in content_node.text.lower():
                    logger.info(f"  -> VALID: High quality and keyword found.")
                    valid_pages.append({
                        "url": url, 
                        "title": content_node.tag, 
                        "text_snippet": content_node.text[:100],
                        "sqs": content_node.sqs_score
                    })
                    # ここでショートカット生成などのアクションを呼び出す
                    # create_shortcut(url, content_node.tag)
                elif content_node.quality_category == "Low Quality":
                     logger.warning(f"  -> LOW QUALITY: Page might contain dummy results.")
                else:
                    logger.warning(f"  -> INVALID: Low quality or keyword not found.")
            else:
                logger.warning(f"  -> Could not extract content from {url}")
        except Exception as e:
            logger.error(f"  -> Failed to process {url}: {e}")

    # 5. 最終結果の表示
    logger.info("\n--- Validation Complete ---")
    if valid_pages:
        logger.info("Found valid pages:")
        for page_info in valid_pages:
            logger.info(f"  - URL: {page_info['url']} (SQS: {page_info['sqs']:.2f})")
    else:
        logger.info("No valid pages were found.")

if __name__ == "__main__":
    # ここに検索したい一意性の高い文字列（ユーザー名など）を指定します
    KEYWORD_TO_SEARCH = "playwright" 
    asyncio.run(main(KEYWORD_TO_SEARCH))
