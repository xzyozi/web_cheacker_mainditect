"""web-cheackerV3.py の純粋ロジック（時刻・通知可否・状態管理・スキャン方針決定）のテスト。

WCM-DD-001 §3.2、§3.3、§3.9 の振る舞いを対象とする。ブラウザとメール送信はモック化する。
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests
from test_web_cheacker import _load_web_checker_module

from content_extractor.dom_treeSt import DOMTreeSt


@pytest.fixture(scope="module")
def mod():
    return _load_web_checker_module()


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# --- 時刻 ---------------------------------------------------------------


@pytest.mark.parametrize("value", ["", None, 123])
def test_safe_parse_datetime_returns_epoch_for_empty_or_non_string(mod, value):
    assert mod.safe_parse_datetime(value) == EPOCH


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2024-01-02T03:04:05Z", datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
        ("2024-01-02T12:04:05+09:00", datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
        ("2024-01-02 03:04:05", datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
        ("20240102 03:04:05", datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)),
        ("2024/01/02 03:04", datetime(2024, 1, 2, 3, 4, tzinfo=timezone.utc)),
        ("2024/01/02", datetime(2024, 1, 2, tzinfo=timezone.utc)),
    ],
)
def test_safe_parse_datetime_accepts_iso_and_legacy_formats_as_utc(mod, text, expected):
    """ISO 8601 を先に試し、旧形式は UTC として解釈する（WCM-DD-001 §2.3）。"""
    assert mod.safe_parse_datetime(text) == expected


def test_safe_parse_datetime_falls_back_to_epoch_for_unparseable_text(mod):
    assert mod.safe_parse_datetime("not a date") == EPOCH


def test_get_strdatetime_is_utc_iso8601_with_z_suffix(mod):
    value = mod.get_Strdatetime()

    assert value.endswith("Z")
    assert mod.safe_parse_datetime(value).tzinfo is not None


# --- Last-Modified / URL整形 ----------------------------------------------


def test_get_last_modified_formats_header_value(mod):
    response = MagicMock(headers={"Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"})
    with patch.object(mod.requests, "head", return_value=response):
        assert mod.get_last_modified("https://example.com") == "2015-10-21 07:28:00"


def test_get_last_modified_returns_none_without_header(mod):
    with patch.object(mod.requests, "head", return_value=MagicMock(headers={})):
        assert mod.get_last_modified("https://example.com") is None


def test_get_last_modified_returns_none_on_request_error(mod):
    with patch.object(mod.requests, "head", side_effect=requests.ConnectionError("down")):
        assert mod.get_last_modified("https://example.com") is None


def test_get_last_modified_returns_none_on_unparseable_header(mod):
    response = MagicMock(headers={"Last-Modified": "garbage"})
    with patch.object(mod.requests, "head", return_value=response):
        assert mod.get_last_modified("https://example.com") is None


def test_remove_encoded_chars_strips_percent_escapes(mod):
    assert mod.remove_encoded_chars("a%20b%2Fc") == "abc"


# --- 通知の可否（NotificationManager） --------------------------------------


def _manager(mod, config):
    user = SimpleNamespace(config=config, send_resultmail=MagicMock())
    return mod.NotificationManager(user), user


@pytest.mark.asyncio
async def test_update_notification_is_skipped_without_diff(mod):
    manager, user = _manager(mod, {"notification": {"type": "email"}})

    await manager.send_update_notification([], [])

    user.send_resultmail.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [{}, {"notification": {"type": "none"}}])
async def test_update_notification_is_skipped_unless_type_is_email(mod, config):
    """TR-024: notification.type が email 以外なら更新通知を送らない。"""
    manager, user = _manager(mod, config)

    await manager.send_update_notification(["https://example.com"], [None])

    user.send_resultmail.assert_not_called()


@pytest.mark.asyncio
async def test_update_notification_sends_generated_html_with_images(mod):
    manager, user = _manager(mod, {"notification": {"type": "email"}})

    with patch.object(mod.text_struct, "generate_html", return_value="<html/>") as generate:
        await manager.send_update_notification(["https://example.com"], ["a.png"])

    generate.assert_called_once_with(["https://example.com"], ["a.png"])
    user.send_resultmail.assert_called_once_with("<html/>", body_type="html", image_list=["a.png"])


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"notification": {"type": "none", "notify_on_error": True}},
        {"notification": {"type": "email"}},
        {"notification": {"type": "email", "notify_on_error": False}},
    ],
)
def test_error_notification_requires_email_type_and_notify_on_error(mod, config):
    manager, user = _manager(mod, config)

    manager.send_error_notification([["https://example.com", "boom"]])

    user.send_resultmail.assert_not_called()


def test_error_notification_is_skipped_for_empty_error_list(mod):
    manager, user = _manager(mod, {"notification": {"type": "email", "notify_on_error": True}})

    manager.send_error_notification([])

    user.send_resultmail.assert_not_called()


def test_error_notification_escapes_html_in_messages(mod):
    """TR-025: エラー文言は HTML エスケープして本文へ入れる。"""
    manager, user = _manager(mod, {"notification": {"type": "email", "notify_on_error": True}})

    manager.send_error_notification([["https://example.com", "<script>alert(1)</script>"]])

    body = user.send_resultmail.call_args.args[0]
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
    assert user.send_resultmail.call_args.kwargs == {"body_type": "html"}


# --- DataManager ----------------------------------------------------------


def _write_urls(path, rows):
    path.write_text(json.dumps(rows), encoding="utf-8")
    return str(path)


def _row(url="https://example.com/news", **overrides):
    row = {
        "url": url,
        "run_code": "",
        "result_vl": "",
        "updated_datetime": "",
        "full_scan_datetime": "",
        "css_selector_list": [],
        "web_page_type": "",
        "image_filename": "",
    }
    row.update(overrides)
    return row


def _tree(links=("https://example.com/a",), url="https://example.com/news", selectors=("main.x",), web_type="plane"):
    node = DOMTreeSt(links=list(links), css_selector_list=list(selectors), web_type=web_type)
    node.url = url
    return node


def _hash(links):
    return hashlib.sha256(str(list(links)).encode()).hexdigest()


def test_data_manager_starts_empty_with_required_columns_when_file_is_missing(mod, tmp_path):
    """TR-002: ファイルが無くても、必須列を持つ空の状態で開始できる。"""
    manager = mod.DataManager(str(tmp_path / "missing.json"))

    assert len(manager.df) == 0
    assert {"url", "result_vl", "css_selector_list", "web_page_type", "image_filename"} <= set(manager.df.columns)


def test_data_manager_starts_empty_when_json_is_invalid(mod, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    assert len(mod.DataManager(str(path)).df) == 0


def test_data_manager_fills_missing_columns_and_null_values(mod, tmp_path):
    """旧形式のレコードを読み込むとき、不足列を補い、null を空文字にする。"""
    path = _write_urls(
        tmp_path / "old.json",
        [{"url": "https://example.com", "result_vl": None, "web_page_type": None, "full_scan_datetime": None}],
    )

    manager = mod.DataManager(path)
    record = manager.get_record_as_dict(0)

    assert record["css_selector_list"] == []
    assert record["image_filename"] == ""
    assert record["result_vl"] == ""
    assert record["web_page_type"] == ""
    assert record["full_scan_datetime"] == ""


def test_update_scan_result_stores_links_hash_selectors_type_and_new_url(mod, tmp_path):
    manager = mod.DataManager(_write_urls(tmp_path / "u.json", [_row()]))
    tree = _tree(links=["https://example.com/a", "https://example.com/b"], url="https://example.com/news?page=2")

    manager.update_scan_result(0, tree)

    record = manager.get_record_as_dict(0)
    assert record["result_vl"] == _hash(tree.links)
    assert record["css_selector_list"] == ["main.x"]
    assert record["web_page_type"] == "plane"
    assert record["url"] == "https://example.com/news?page=2"
    assert record["updated_datetime"].endswith("Z")


def test_clear_scan_data_keeps_hash_but_forces_next_full_scan(mod, tmp_path):
    """TR-005: セレクタ一覧とFull日時だけを消し、ハッシュと更新日時は保持する。"""
    path = _write_urls(
        tmp_path / "u.json",
        [_row(result_vl="abc", updated_datetime="t", full_scan_datetime="f", css_selector_list=["x"])],
    )
    manager = mod.DataManager(path)

    manager.clear_scan_data(0)

    record = manager.get_record_as_dict(0)
    assert record["css_selector_list"] == []
    assert record["full_scan_datetime"] == ""
    assert record["result_vl"] == "abc"
    assert record["updated_datetime"] == "t"


def test_update_image_filename_stores_basename_only(mod, tmp_path):
    manager = mod.DataManager(_write_urls(tmp_path / "u.json", [_row("https://a.example"), _row("https://b.example")]))

    manager.update_image_filename("https://b.example", str(tmp_path / "images" / "shot.png"))

    assert manager.df["image_filename"].tolist() == ["", "shot.png"]


def test_chk_diff_returns_only_urls_whose_hash_changed(mod, tmp_path):
    """TR-004: result_vl が変化した行のURLだけを返す。"""
    path = _write_urls(
        tmp_path / "u.json",
        [_row("https://same.example", result_vl="h1"), _row("https://changed.example", result_vl="h2")],
    )
    manager = mod.DataManager(path)
    manager.update_scan_result(1, _tree(url="https://changed.example"))

    assert manager.chk_diff() == ["https://changed.example"]


def test_chk_diff_treats_first_scan_as_a_difference(mod, tmp_path):
    manager = mod.DataManager(_write_urls(tmp_path / "u.json", [_row()]))
    manager.update_scan_result(0, _tree())

    assert manager.chk_diff() == ["https://example.com/news"]


def test_save_data_stamps_run_code_on_every_row(mod, tmp_path):
    path = tmp_path / "u.json"
    manager = mod.DataManager(_write_urls(path, [_row("https://a.example"), _row("https://b.example")]))

    manager.save_data()

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len({row["run_code"] for row in saved}) == 1
    assert saved[0]["run_code"].endswith("Z")
    assert not (tmp_path / "u.json.tmp").exists()


# --- process_url_async（スキャン方針決定） -----------------------------------


def _scan_env(mod, tmp_path, row):
    manager = mod.DataManager(_write_urls(tmp_path / "u.json", [row]))
    return manager, [], asyncio.Semaphore(1)


async def _run(mod, manager, errors, semaphore, config=None, url="https://example.com/news"):
    await mod.process_url_async(url, 0, manager, errors, config or {}, semaphore, MagicMock())


def _quick_ready_row(mod, **overrides):
    return _row(
        result_vl=_hash(["https://example.com/a"]),
        updated_datetime="before",
        full_scan_datetime=mod.get_Strdatetime(),
        css_selector_list=["main.x"],
        web_page_type="plane",
        **overrides,
    )


@pytest.mark.asyncio
async def test_quick_scan_with_same_links_leaves_state_unchanged(mod, tmp_path):
    """TR-006、TR-008: Quick条件を満たすときはQuickを使い、同じリンク集合なら状態を更新しない。"""
    manager, errors, semaphore = _scan_env(mod, tmp_path, _quick_ready_row(mod))

    with (
        patch.object(mod, "quick_extract_content", new=AsyncMock(return_value=_tree())) as quick,
        patch.object(mod, "extract_main_content", new=AsyncMock()) as full,
    ):
        await _run(mod, manager, errors, semaphore)

    quick.assert_awaited_once()
    full.assert_not_called()
    assert manager.get_record_as_dict(0)["updated_datetime"] == "before"
    assert errors == []


@pytest.mark.asyncio
async def test_quick_scan_with_changed_links_updates_state(mod, tmp_path):
    manager, errors, semaphore = _scan_env(mod, tmp_path, _quick_ready_row(mod))
    tree = _tree(links=["https://example.com/new"])

    with patch.object(mod, "quick_extract_content", new=AsyncMock(return_value=tree)):
        await _run(mod, manager, errors, semaphore)

    record = manager.get_record_as_dict(0)
    assert record["result_vl"] == _hash(tree.links)
    assert record["updated_datetime"] != "before"


@pytest.mark.asyncio
async def test_full_scan_is_used_when_last_full_scan_is_four_days_old(mod, tmp_path):
    """TR-006: Full実施から4日以上経過していればQuickを試さない。"""
    old = "2000-01-01T00:00:00Z"
    manager, errors, semaphore = _scan_env(mod, tmp_path, _quick_ready_row(mod) | {"full_scan_datetime": old})

    with (
        patch.object(mod, "quick_extract_content", new=AsyncMock()) as quick,
        patch.object(mod, "extract_main_content", new=AsyncMock(return_value=_tree())) as full,
    ):
        await _run(mod, manager, errors, semaphore)

    quick.assert_not_called()
    full.assert_awaited_once()
    assert manager.get_record_as_dict(0)["full_scan_datetime"] != old


@pytest.mark.asyncio
async def test_quick_failure_falls_back_to_full_scan(mod, tmp_path):
    manager, errors, semaphore = _scan_env(mod, tmp_path, _quick_ready_row(mod))

    with (
        patch.object(mod, "quick_extract_content", new=AsyncMock(return_value=None)),
        patch.object(mod, "extract_main_content", new=AsyncMock(return_value=_tree())) as full,
    ):
        await _run(mod, manager, errors, semaphore)

    full.assert_awaited_once()
    assert errors == []


@pytest.mark.asyncio
async def test_full_scan_returning_none_records_error_and_clears_selectors(mod, tmp_path):
    """TR-007: Full失敗時はエラー一覧へ追加し、次回Fullを促す。"""
    manager, errors, semaphore = _scan_env(mod, tmp_path, _row())

    with patch.object(mod, "extract_main_content", new=AsyncMock(return_value=None)):
        await _run(mod, manager, errors, semaphore)

    assert errors == [["https://example.com/news", "Full scan returned None"]]
    assert manager.get_record_as_dict(0)["css_selector_list"] == []


@pytest.mark.asyncio
async def test_full_scan_empty_result_page_records_error_and_keeps_hash(mod, tmp_path):
    manager, errors, semaphore = _scan_env(mod, tmp_path, _row(result_vl="keep", css_selector_list=["x"]))
    empty = _tree()
    empty.is_empty_result = True

    with patch.object(mod, "extract_main_content", new=AsyncMock(return_value=empty)):
        await _run(mod, manager, errors, semaphore)

    assert errors == [["https://example.com/news", "Empty result page detected"]]
    record = manager.get_record_as_dict(0)
    assert record["css_selector_list"] == []
    assert record["result_vl"] == "keep"


@pytest.mark.asyncio
async def test_first_scan_always_writes_state_even_if_hash_is_unchanged(mod, tmp_path):
    """web_page_type が空（初回）のときは、ハッシュが同じでも状態を保存する。"""
    tree = _tree()
    manager, errors, semaphore = _scan_env(mod, tmp_path, _row(result_vl=_hash(tree.links)))

    with patch.object(mod, "extract_main_content", new=AsyncMock(return_value=tree)):
        await _run(mod, manager, errors, semaphore)

    record = manager.get_record_as_dict(0)
    assert record["web_page_type"] == "plane"
    assert record["css_selector_list"] == ["main.x"]


@pytest.mark.asyncio
async def test_slow_scan_is_recorded_as_error_without_aborting(mod, tmp_path):
    """処理時間が timeout_per_url を超えた場合は、エラー一覧へ記録する（中断はしない）。"""
    manager, errors, semaphore = _scan_env(mod, tmp_path, _row())

    with patch.object(mod, "extract_main_content", new=AsyncMock(return_value=_tree())):
        await _run(mod, manager, errors, semaphore, config={"scan": {"timeout_per_url": -1}})

    assert len(errors) == 1
    assert "exceeded" in errors[0][1]
    assert manager.get_record_as_dict(0)["web_page_type"] == "plane"
