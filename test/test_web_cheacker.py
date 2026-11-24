import asyncio
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml


def _load_web_checker_module():
    """`web-cheackerV3.py` をログファイル生成の副作用なしに読み込む。"""
    module_path = Path(__file__).resolve().parent.parent / "src" / "web-cheackerV3.py"
    test_logger = logging.getLogger("test_web_cheacker_v3_main")
    test_logger.setLevel(logging.DEBUG)
    test_logger.propagate = True

    spec = importlib.util.spec_from_file_location("web_cheacker_v3_main_under_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch("utils.setup_logger.setup_logger", return_value=test_logger):
        spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def web_checker_module():
    return _load_web_checker_module()


def _setup_workspace(tmp_path: Path, temp_dir: Path) -> None:
    """`main()` 実行に必要な一時ユーザーディレクトリと設定ファイルを作成する。"""
    user_dir = tmp_path / "users" / "jav"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "mail.yaml").write_text(
        yaml.safe_dump({"gmail": {"receiver_mail": "to@example.com", "account": "from@example.com", "password": "pw"}}),
        encoding="utf-8",
    )
    (user_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "notification": {"type": "email"},
                "scan": {"worker_threads": 1},
                "screenshot": {
                    "enabled": True,
                    "temporary_dir": str(temp_dir),
                    "email_width": 500,
                    "permanent_width": 1920,
                },
            }
        ),
        encoding="utf-8",
    )
    (user_dir / "cheacker_url.json").write_text(
        json.dumps(
            [
                {
                    "url": "https://example.com/page",
                    "run_code": "",
                    "result_vl": "old_hash",
                    "updated_datetime": "",
                    "full_scan_datetime": "",
                    "css_selector_list": [],
                    "web_page_type": "",
                    "image_filename": "",
                }
            ]
        ),
        encoding="utf-8",
    )


def _mock_playwright(monkeypatch, web_checker_module):
    """`async_playwright()` を実ブラウザを起動しないモックへ差し替える。"""
    mock_browser = AsyncMock()
    mock_playwright = MagicMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(web_checker_module, "async_playwright", lambda: mock_cm)
    return mock_browser


@pytest.mark.asyncio
async def test_main_cleans_temp_dir_when_save_screenshot_raises(tmp_path, monkeypatch, web_checker_module):
    """`save_screenshot` が `temp_dir` 作成後に例外を送出しても `temp_dir` が確実に削除される。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["web-cheackerV3.py", "jav"])
    temp_dir = tmp_path / "temp_screenshots"
    _setup_workspace(tmp_path, temp_dir)
    mock_browser = _mock_playwright(monkeypatch, web_checker_module)

    async def fake_process_url(url, index_num, data_manager, error_list, config, semaphore, browser):
        data_manager.df.at[index_num, "result_vl"] = "new_hash"

    async def fake_save_screenshot(browser, url_list, save_dir, width):
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        (Path(save_dir) / "shot.png").write_bytes(b"png")
        raise RuntimeError("screenshot failed")

    monkeypatch.setattr(web_checker_module, "process_url_async", fake_process_url)
    monkeypatch.setattr(web_checker_module, "save_screenshot", fake_save_screenshot)

    with pytest.raises(RuntimeError, match="screenshot failed"):
        await web_checker_module.main()

    assert not temp_dir.exists()
    mock_browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_cleans_temp_dir_when_notification_raises(tmp_path, monkeypatch, web_checker_module):
    """通知送信中に例外が発生した場合も、作成済みの `temp_dir` が確実に削除される。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["web-cheackerV3.py", "jav"])
    temp_dir = tmp_path / "temp_screenshots"
    _setup_workspace(tmp_path, temp_dir)
    mock_browser = _mock_playwright(monkeypatch, web_checker_module)

    async def fake_process_url(url, index_num, data_manager, error_list, config, semaphore, browser):
        data_manager.df.at[index_num, "result_vl"] = "new_hash"

    async def fake_save_screenshot(browser, url_list, save_dir, width):
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        shot = Path(save_dir) / "shot.png"
        shot.write_bytes(b"png")
        return [str(shot)]

    async def fake_send_update_notification(self, diff_urls, image_list):
        assert temp_dir.is_dir()
        raise RuntimeError("mail failed")

    monkeypatch.setattr(web_checker_module, "process_url_async", fake_process_url)
    monkeypatch.setattr(web_checker_module, "save_screenshot", fake_save_screenshot)
    monkeypatch.setattr(
        web_checker_module.NotificationManager,
        "send_update_notification",
        fake_send_update_notification,
    )

    with pytest.raises(RuntimeError, match="mail failed"):
        await web_checker_module.main()

    assert not temp_dir.exists()
    mock_browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_cleans_temp_dir_when_async_playwright_raises(tmp_path, monkeypatch, web_checker_module):
    """`async_playwright` 内で例外が発生しても、前処理後の保護範囲としてクリーンアップが実行される。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["web-cheackerV3.py", "jav"])
    temp_dir = tmp_path / "temp_screenshots"
    _setup_workspace(tmp_path, temp_dir)

    mock_playwright = MagicMock()
    mock_playwright.chromium.launch = AsyncMock(side_effect=RuntimeError("launch failed"))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(web_checker_module, "async_playwright", lambda: mock_cm)

    cleanup_calls: list[str] = []
    original_cleanup = web_checker_module._cleanup_temp_dir

    def spy_cleanup(path: str) -> None:
        cleanup_calls.append(path)
        original_cleanup(path)

    monkeypatch.setattr(web_checker_module, "_cleanup_temp_dir", spy_cleanup)

    with pytest.raises(RuntimeError, match="launch failed"):
        await web_checker_module.main()

    assert cleanup_calls == [str(temp_dir), str(temp_dir)]
    assert not temp_dir.exists()


def _write_sample_data_file(file_path: Path) -> str:
    """DataManager テスト用の初期 JSON ファイルを作成し、元のテキストを返す。"""
    records = [
        {
            "url": "https://example.com/page",
            "run_code": "2026-01-01T00:00:00Z",
            "result_vl": "old_hash",
            "updated_datetime": "2026-01-01T00:00:00Z",
            "full_scan_datetime": "",
            "css_selector_list": ["main.content"],
            "web_page_type": "plane",
            "image_filename": "",
        }
    ]
    raw = json.dumps(records, ensure_ascii=False, indent=4)
    file_path.write_text(raw, encoding="utf-8")
    return raw


def test_data_manager_save_data_atomic_via_tmp_and_os_replace(tmp_path, monkeypatch, web_checker_module):
    """DataManager.save_data が一時ファイル (.tmp) 経由で os.replace により原子的に保存することを確認する。"""
    data_file = tmp_path / "cheacker_url.json"
    _write_sample_data_file(data_file)
    dm = web_checker_module.DataManager(str(data_file))
    dm.df.at[0, "result_vl"] = "updated_hash"

    replace_calls: list[tuple[str, str]] = []
    original_replace = os.replace

    def spy_replace(src: str, dst: str) -> None:
        assert Path(src).exists()
        replace_calls.append((src, dst))
        original_replace(src, dst)

    monkeypatch.setattr(web_checker_module.os, "replace", spy_replace)

    dm.save_data()

    expected_tmp = f"{data_file}.tmp"
    assert replace_calls == [(expected_tmp, str(data_file))]
    assert not Path(expected_tmp).exists()

    saved = json.loads(data_file.read_text(encoding="utf-8"))
    assert len(saved) == 1
    assert saved[0]["result_vl"] == "updated_hash"
    assert saved[0]["run_code"] != "2026-01-01T00:00:00Z"


def test_data_manager_save_data_preserves_original_file_on_write_failure(tmp_path, monkeypatch, web_checker_module):
    """書き込み途中で失敗しても os.replace が呼ばれず、元の JSON ファイルが破損しないことを確認する。"""
    data_file = tmp_path / "cheacker_url.json"
    original_raw = _write_sample_data_file(data_file)
    dm = web_checker_module.DataManager(str(data_file))
    dm.df.at[0, "result_vl"] = "unsaved_hash"

    def failing_to_json(path_or_buf, *args, **kwargs):
        Path(path_or_buf).write_text('{"broken": ', encoding="utf-8")
        raise OSError("disk full during temp write")

    replace_mock = MagicMock()
    monkeypatch.setattr(dm.df, "to_json", failing_to_json)
    monkeypatch.setattr(web_checker_module.os, "replace", replace_mock)

    with pytest.raises(OSError, match="disk full during temp write"):
        dm.save_data()

    replace_mock.assert_not_called()
    assert data_file.read_text(encoding="utf-8") == original_raw
    intact = json.loads(data_file.read_text(encoding="utf-8"))
    assert intact[0]["result_vl"] == "old_hash"


@pytest.mark.asyncio
async def test_process_url_async_records_error_list_and_clears_data_on_failure(
    tmp_path, monkeypatch, web_checker_module
):
    """Full スキャン失敗時と例外発生時に error_list へ記録され、後続処理が落ちないことを確認する。"""
    data_file = tmp_path / "cheacker_url.json"
    _write_sample_data_file(data_file)
    dm = web_checker_module.DataManager(str(data_file))
    error_list: list = []
    semaphore = asyncio.Semaphore(1)
    mock_browser = AsyncMock()

    monkeypatch.setattr(web_checker_module, "extract_main_content", AsyncMock(return_value=None))
    await web_checker_module.process_url_async(
        "https://example.com/page", 0, dm, error_list, {}, semaphore, mock_browser
    )

    assert error_list == [["https://example.com/page", "Full scan returned None"]]
    assert dm.df.at[0, "css_selector_list"] == []
    assert dm.df.at[0, "full_scan_datetime"] == ""

    error_list.clear()
    monkeypatch.setattr(web_checker_module, "extract_main_content", AsyncMock(side_effect=RuntimeError("boom")))
    await web_checker_module.process_url_async(
        "https://example.com/page", 0, dm, error_list, {}, semaphore, mock_browser
    )

    assert len(error_list) == 1
    assert error_list[0][0] == "https://example.com/page"
    assert isinstance(error_list[0][1], RuntimeError)
    assert str(error_list[0][1]) == "boom"
