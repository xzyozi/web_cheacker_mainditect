import importlib.util
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


def _load_web_checker_module():
    """`web-cheackerV3.py` をログファイル生成の副作用なしに読み込む。"""
    module_path = Path(__file__).resolve().parent.parent / "src" / "web-cheackerV3.py"
    test_logger = logging.getLogger("test_web_cheacker_v3")
    test_logger.setLevel(logging.DEBUG)
    test_logger.propagate = True

    spec = importlib.util.spec_from_file_location("web_cheacker_v3_under_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch("utils.setup_logger.setup_logger", return_value=test_logger):
        spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def web_checker_module():
    return _load_web_checker_module()


def _prepare_user_dir(base_dir: Path, username: str = "jav") -> Path:
    user_dir = base_dir / "users" / username
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "mail.yaml").write_text(
        yaml.safe_dump({"gmail": {"receiver_mail": "a@example.com", "account": "b@example.com", "password": "pw"}}),
        encoding="utf-8",
    )
    return user_dir


def test_load_app_config_prefers_user_config(tmp_path, monkeypatch, caplog, web_checker_module):
    """ユーザー側と共通側の両方がある場合はユーザー側の config.yaml を優先して読み込む。"""
    monkeypatch.chdir(tmp_path)
    user_dir = _prepare_user_dir(tmp_path, "jav")
    (tmp_path / "users" / "config.yaml").write_text(
        yaml.safe_dump({"notification": {"type": "none"}, "scan": {"worker_threads": 1}}),
        encoding="utf-8",
    )
    (user_dir / "config.yaml").write_text(
        yaml.safe_dump({"notification": {"type": "email"}, "scan": {"worker_threads": 4}}),
        encoding="utf-8",
    )

    with caplog.at_level(logging.INFO, logger="test_web_cheacker_v3"):
        user = web_checker_module.User("jav")

    expected_path = str(Path("users") / "jav" / "config.yaml")
    assert user.config == {"notification": {"type": "email"}, "scan": {"worker_threads": 4}}
    assert any(
        record.levelno == logging.INFO and f"Loaded app config from {expected_path}" in record.message
        for record in caplog.records
    )


def test_load_app_config_falls_back_to_common_config(tmp_path, monkeypatch, caplog, web_checker_module):
    """ユーザー側に無く共通側だけにある場合は users/config.yaml を読み込む。"""
    monkeypatch.chdir(tmp_path)
    _prepare_user_dir(tmp_path, "jav")
    (tmp_path / "users" / "config.yaml").write_text(
        yaml.safe_dump({"notification": {"type": "email"}, "screenshot": {"enabled": True}}),
        encoding="utf-8",
    )

    with caplog.at_level(logging.INFO, logger="test_web_cheacker_v3"):
        user = web_checker_module.User("jav")

    expected_path = str(Path("users") / "config.yaml")
    assert user.config == {"notification": {"type": "email"}, "screenshot": {"enabled": True}}
    assert any(
        record.levelno == logging.INFO and f"Loaded app config from {expected_path}" in record.message
        for record in caplog.records
    )


def test_load_app_config_warns_and_uses_empty_dict_when_neither_exists(
    tmp_path, monkeypatch, caplog, web_checker_module
):
    """ユーザー側にも共通側にも無い場合は警告を出して空辞書を返す。"""
    monkeypatch.chdir(tmp_path)
    _prepare_user_dir(tmp_path, "jav")

    with caplog.at_level(logging.WARNING, logger="test_web_cheacker_v3"):
        user = web_checker_module.User("jav")

    assert user.config == {}
    assert any(
        record.levelno == logging.WARNING and "App config file not found" in record.message for record in caplog.records
    )


def test_load_app_config_handles_empty_yaml_as_empty_dict(tmp_path, monkeypatch, web_checker_module):
    """空の config.yaml（yaml.safe_load が None を返す）でも空辞書になる。"""
    monkeypatch.chdir(tmp_path)
    user_dir = _prepare_user_dir(tmp_path, "jav")
    (user_dir / "config.yaml").write_text("", encoding="utf-8")

    user = web_checker_module.User("jav")
    assert user.config == {}


def test_load_app_config_handles_invalid_yaml_as_empty_dict(tmp_path, monkeypatch, caplog, web_checker_module):
    """不正な YAML 構文時はエラーログを出して空辞書を返す。"""
    monkeypatch.chdir(tmp_path)
    user_dir = _prepare_user_dir(tmp_path, "jav")
    (user_dir / "config.yaml").write_text("scan: [invalid", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="test_web_cheacker_v3"):
        user = web_checker_module.User("jav")

    assert user.config == {}
    assert any(
        record.levelno == logging.ERROR and "Error loading app config" in record.message for record in caplog.records
    )


def test_send_resultmail_uses_fresh_empty_image_list_by_default(tmp_path, monkeypatch, web_checker_module):
    """send_resultmail で image_list 省略時に新しい空リストが使われる（B006 対策）。"""
    monkeypatch.chdir(tmp_path)
    _prepare_user_dir(tmp_path, "jav")
    user = web_checker_module.User("jav")

    with patch.object(web_checker_module, "send_email") as mock_send:
        user.send_resultmail("body", "html")
        passed_images = mock_send.call_args.kwargs["image_list"]
        assert passed_images == []
        passed_images.append("mutated.png")

        user.send_resultmail("body2", "html")
        assert mock_send.call_args.kwargs["image_list"] == []
