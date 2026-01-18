import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, Page, Browser, ElementHandle, BrowserContext
import aiohttp
import os
from PIL import Image
import asyncio # For patching asyncio.sleep

from content_extractor.playwright_helpers import (
    setup_page,
    adjust_page_view,
    fetch_robots_txt,
    is_scraping_allowed,
    save_screenshot,
    generate_filename
)

# --- Fixtures for Playwright and Aiohttp Mocks ---

@pytest.fixture
def mock_browser():
    return AsyncMock(spec=Browser)

@pytest.fixture
def mock_context(mock_browser):
    context = AsyncMock(spec=BrowserContext)
    mock_browser.new_context.return_value = context
    return context

@pytest.fixture
def mock_page(mock_context):
    page = AsyncMock(spec=Page)
    mock_context.new_page.return_value = page
    return page

@pytest.fixture
def mock_aiohttp_response():
    response = AsyncMock()
    response.status = 200
    response.text.return_value = "User-agent: *\nAllow: /"
    return response

@pytest.fixture(autouse=True)
def mock_asyncio_sleep(mocker):
    # Patch asyncio.sleep to prevent actual delays during tests
    return mocker.patch('asyncio.sleep', new=AsyncMock())


# --- Tests for fetch_robots_txt ---

@pytest.mark.asyncio
@patch('content_extractor.playwright_helpers.aiohttp.ClientSession')
async def test_fetch_robots_txt_success(MockClientSession, mock_aiohttp_response):
    """Test Case 1: 正常な`robots.txt`の取得"""
    # Arrange
    get_context = AsyncMock()
    get_context.__aenter__.return_value = mock_aiohttp_response
    session = MagicMock()
    session.get.return_value = get_context
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    MockClientSession.return_value = session_context

    # Act
    url = "http://example.com/some/path"
    robots_content = await fetch_robots_txt(url)

    # Assert
    assert robots_content == "User-agent: *\nAllow: /"
    session.get.assert_called_once_with("http://example.com/robots.txt")

@pytest.mark.asyncio
@patch('content_extractor.playwright_helpers.aiohttp.ClientSession')
async def test_fetch_robots_txt_not_found(MockClientSession, mock_aiohttp_response):
    """Test Case 2: `robots.txt`が見つからない (404)"""
    # Arrange
    mock_aiohttp_response.status = 404
    get_context = AsyncMock()
    get_context.__aenter__.return_value = mock_aiohttp_response
    session = MagicMock()
    session.get.return_value = get_context
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    MockClientSession.return_value = session_context

    # Act
    url = "http://example.com/some/path"
    robots_content = await fetch_robots_txt(url)

    # Assert
    assert robots_content is None
    session.get.assert_called_once()

@pytest.mark.asyncio
@patch('content_extractor.playwright_helpers.aiohttp.ClientSession')
async def test_fetch_robots_txt_network_error(MockClientSession):
    """Test Case 3: ネットワークエラー"""
    # Arrange: session.get() will raise a ClientError
    session = MagicMock()
    session.get.side_effect = aiohttp.ClientError("Network Error")
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    MockClientSession.return_value = session_context

    # Act
    url = "http://example.com/some/path"
    robots_content = await fetch_robots_txt(url)

    # Assert
    assert robots_content is None
    session.get.assert_called_once()



# --- Tests for is_scraping_allowed ---

def test_is_scraping_allowed_allowed_path():
    """Test Case 1: 許可されているパス"""
    robots_txt = "User-agent: *\nDisallow: /admin\nAllow: /public"
    assert is_scraping_allowed(robots_txt, "/public/page") is True
    assert is_scraping_allowed(robots_txt, "/another/path") is True # Not explicitly disallowed

def test_is_scraping_allowed_disallowed_path():
    """Test Case 2: 禁止されているパス"""
    robots_txt = "User-agent: *\nDisallow: /private\nDisallow: /temp"
    assert is_scraping_allowed(robots_txt, "/private/data") is False
    assert is_scraping_allowed(robots_txt, "/temp/file.html") is False

def test_is_scraping_allowed_empty_robots_txt():
    """Test Case 3: `robots.txt`が存在しない（空の文字列）"""
    robots_txt = ""
    assert is_scraping_allowed(robots_txt, "/any/path") is True
    assert is_scraping_allowed(robots_txt, "/admin") is True

def test_is_scraping_allowed_comment_and_empty_lines():
    """Test Case 4: コメント行と空行の処理"""
    robots_txt = """
# This is a comment
User-agent: *

Disallow: /secret
"""
    assert is_scraping_allowed(robots_txt, "/secret/page") is False
    assert is_scraping_allowed(robots_txt, "/public/page") is True

# --- Tests for generate_filename ---

def test_generate_filename_basic_url():
    """Test Case 1: 基本的なURLからの生成"""
    url = "https://example.com/some/path/page.html"
    filename = generate_filename(url)
    assert filename.startswith("example_com_page.html_")
    assert filename.endswith(".png")
    assert len(filename) > len("example_com_page.html_.png") # Check for hash

def test_generate_filename_url_with_query_params():
    """Test Case 2: クエリパラメータを含むURL"""
    url = "https://example.com/page?param=value&id=123"
    filename = generate_filename(url)
    assert filename.startswith("example_com_page_")
    assert filename.endswith(".png")
    # Should not contain query params in the readable part
    assert "param" not in filename and "value" not in filename

def test_generate_filename_url_with_special_characters():
    """Test Case 3: 特殊文字を含むURL"""
    url = "https://example.com/path/with spaces/file!.html"
    filename = generate_filename(url)
    # The actual generated part will have 'file!.html' as last_part, and spaces from the original path
    # will implicitly be handled by the URL parsing and hash generation.
    assert filename.startswith("example_com_file!.html_") # `last_part` directly includes "file!.html"
    # Spaces are removed during domain processing, but here we check for the original full URL's path part in the filename before hash.
    # The `path_hash` is based on the full path which would include spaces, but `last_part` itself is just 'file!.html'
    # The `domain` part has `_` for `.`, but the `last_part` does not replace spaces with `_`.
    # Let's adjust this to accurately reflect generated string.
    # The `path` for "/path/with spaces/file!.html" is what gets hashed.
    # The `last_part` is "file!.html".
    # The `domain` is "example_com".
    # So the expected prefix is "example_com_file!.html_"
    assert " " not in filename # The filename string itself will not contain literal spaces due to hashing.
    assert filename.endswith(".png")

def test_generate_filename_root_url():
    """Test Case 4: ルートURL"""
    url = "https://example.com"
    filename = generate_filename(url)
    assert filename.startswith("example_com_index_")
    assert filename.endswith(".png")

def test_generate_filename_url_with_trailing_slash():
    """URLが末尾スラッシュを持つ場合のテスト"""
    url = "https://anothersite.org/my/page/"
    filename = generate_filename(url)
    assert filename.startswith("anothersite_org_page_")
    assert filename.endswith(".png")

# --- Tests for save_screenshot (complex, will need more specific mocks) ---

@pytest.mark.asyncio
@patch('os.makedirs')
@patch('os.path.join', side_effect=os.path.join) # Keep original behavior for path joining
@patch('PIL.Image.open')
async def test_save_screenshot_success(mock_image_open, mock_path_join, mock_makedirs,
                                       mock_browser, mock_context, mock_page,
                                       mock_asyncio_sleep):
    """Test Case 1: 正常なスクリーンショットの保存とリサイズ"""
    url = "http://example.com/test"
    test_filepath = os.path.join("temp", generate_filename(url))

    # Mock Playwright calls
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.return_value = None
    mock_page.screenshot.return_value = None

    # Mock PIL.Image calls
    mock_img_instance = MagicMock()
    mock_img_instance.width = 1000
    mock_img_instance.height = 500
    mock_image_open.return_value.__enter__.return_value = mock_img_instance
    mock_img_instance.resize.return_value = mock_img_instance # Resized image is the same mock
    mock_img_instance.save.return_value = None

    result_paths = await save_screenshot(mock_browser, [url], width=200)

    mock_makedirs.assert_called_once_with("temp", exist_ok=True)
    mock_browser.new_context.assert_called_once()
    mock_context.new_page.assert_called_once()
    mock_page.goto.assert_called_once_with(url, wait_until='load', timeout=30000)
    mock_page.screenshot.assert_called_once_with(path=test_filepath, full_page=True)
    mock_image_open.assert_called_once_with(test_filepath)
    # Expected resize: width=200, height= (200 * 500/1000) = 100
    mock_img_instance.resize.assert_called_once_with((200, 100))
    mock_img_instance.save.assert_called_once_with(test_filepath)
    mock_page.close.assert_called_once()
    mock_context.close.assert_called_once()
    assert result_paths == [test_filepath]
    assert mock_asyncio_sleep.call_count == 0

@pytest.mark.asyncio
@patch('os.makedirs')
@patch('os.path.join', side_effect=os.path.join)
@patch('PIL.Image.open')
async def test_save_screenshot_invalid_url(mock_image_open, mock_path_join, mock_makedirs,
                                            mock_browser, mock_asyncio_sleep):
    """Test Case 2: 無効なURLのスキップ"""
    invalid_url = "invalid-url"
    result_paths = await save_screenshot(mock_browser, [invalid_url])
    assert result_paths == [None]
    mock_makedirs.assert_called_once() # Should still try to make dir
    mock_browser.new_context.assert_not_called()
    assert mock_asyncio_sleep.call_count == 0

@pytest.mark.asyncio
@patch('os.makedirs')
@patch('os.path.join', side_effect=os.path.join)
@patch('PIL.Image.open')
async def test_save_screenshot_retry_on_timeout(mock_image_open, mock_path_join, mock_makedirs,
                                                 mock_browser, mock_context, mock_page,
                                                 mock_asyncio_sleep):
    """Test Case 3: リトライメカニズム (PlaywrightTimeoutError)"""
    url = "http://example.com/retry"
    test_filepath = os.path.join("temp", generate_filename(url))

    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    # Fail twice, succeed on third attempt
    mock_page.goto.side_effect = [
        PlaywrightTimeoutError("timeout 1"),
        PlaywrightTimeoutError("timeout 2"),
        None # Success on third try
    ]
    mock_page.screenshot.return_value = None

    mock_img_instance = MagicMock()
    mock_img_instance.width = 1000
    mock_img_instance.height = 500
    mock_image_open.return_value.__enter__.return_value = mock_img_instance
    mock_img_instance.resize.return_value = mock_img_instance
    mock_img_instance.save.return_value = None

    result_paths = await save_screenshot(mock_browser, [url])

    assert result_paths == [test_filepath]
    assert mock_browser.new_context.call_count == 3
    assert mock_context.new_page.call_count == 3
    assert mock_page.goto.call_count == 3
    assert mock_page.screenshot.call_count == 1 # Only called on success
    assert mock_asyncio_sleep.call_count == 2 # Sleep after first two failures

@pytest.mark.asyncio
@patch('os.makedirs')
@patch('os.path.join', side_effect=os.path.join)
@patch('PIL.Image.open')
async def test_save_screenshot_max_retries_exceeded(mock_image_open, mock_path_join, mock_makedirs,
                                                      mock_browser, mock_context, mock_page,
                                                      mock_asyncio_sleep):
    """Test Case 4: 最大リトライ回数を超えた失敗"""
    url = "http://example.com/fail"
    
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    # Always fail
    mock_page.goto.side_effect = PlaywrightTimeoutError("timeout")

    result_paths = await save_screenshot(mock_browser, [url])

    assert result_paths == [None]
    assert mock_browser.new_context.call_count == 3
    assert mock_context.new_page.call_count == 3
    assert mock_page.goto.call_count == 3
    assert mock_page.screenshot.call_count == 0
    assert mock_asyncio_sleep.call_count == 2

@pytest.mark.asyncio
@patch('os.makedirs')
@patch('os.path.join', side_effect=os.path.join)
@patch('PIL.Image.open')
async def test_save_screenshot_aspect_ratio(mock_image_open, mock_path_join, mock_makedirs,
                                            mock_browser, mock_context, mock_page):
    """Test Case 5: 画像リサイズ時のアスペクト比保持"""
    url = "http://example.com/aspect"
    test_filepath = os.path.join("temp", generate_filename(url))

    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.return_value = None
    mock_page.screenshot.return_value = None

    mock_img_instance = MagicMock()
    mock_img_instance.width = 1200
    mock_img_instance.height = 600 # Aspect ratio 2:1
    mock_image_open.return_value.__enter__.return_value = mock_img_instance
    mock_img_instance.resize.return_value = mock_img_instance
    mock_img_instance.save.return_value = None

    # Test with only width specified
    await save_screenshot(mock_browser, [url], width=300, height=None)
    mock_img_instance.resize.assert_called_once_with((300, 150)) # height should be 300 / 2 = 150

    mock_img_instance.resize.reset_mock() # Reset for second assertion
    # Test with both width and height specified (height should override aspect ratio)
    await save_screenshot(mock_browser, [url], width=300, height=400)
    mock_img_instance.resize.assert_called_once_with((300, 400))


@pytest.mark.asyncio
@patch('os.makedirs')
@patch('os.path.join', side_effect=os.path.join)
@patch('PIL.Image.open')
async def test_save_screenshot_makedirs_called(mock_image_open, mock_path_join, mock_makedirs,
                                                mock_browser, mock_context, mock_page):
    """Test Case 6: ディレクトリの作成"""
    url = "http://example.com/makedirs"
    test_filepath = os.path.join("new_temp_dir", generate_filename(url))

    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.return_value = None
    mock_page.screenshot.return_value = None
    mock_image_open.return_value.__enter__.return_value = MagicMock() # Minimal mock for image operations

    await save_screenshot(mock_browser, [url], save_dir="new_temp_dir")
    mock_makedirs.assert_called_once_with("new_temp_dir", exist_ok=True)
