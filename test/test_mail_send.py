"""mail.send_email（Gmail SMTP送信）のテスト。SMTP接続はモック化する。"""

from unittest.mock import patch

import pytest

from mail import send_email

CONFIG = {"gmail": {"account": "sender@example.com", "password": "app-password"}}
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _send(**kwargs):
    with patch("mail.test_send_mail.smtplib.SMTP") as smtp_cls:
        smtp = smtp_cls.return_value
        send_email(CONFIG, "receiver@example.com", **kwargs)
    sent_message = smtp.sendmail.call_args.args[2]
    return smtp_cls, smtp, sent_message


def test_connects_with_starttls_then_logs_in_and_sends():
    """smtp.gmail.com:587 へ接続し、STARTTLS後にログインして1通送り、接続を閉じる。"""
    smtp_cls, smtp, _ = _send(body="hello")

    smtp_cls.assert_called_once_with("smtp.gmail.com", 587)
    method_names = [call[0] for call in smtp.method_calls]
    assert method_names.index("starttls") < method_names.index("login") < method_names.index("sendmail")
    smtp.login.assert_called_once_with("sender@example.com", "app-password")
    assert smtp.sendmail.call_args.args[:2] == ("sender@example.com", "receiver@example.com")
    smtp.close.assert_called_once()


def test_html_body_is_sent_with_requested_type():
    _, _, message = _send(body="<p>更新</p>", body_type="html")

    assert "Content-Type: text/html" in message
    assert "From: sender@example.com" in message
    assert "To: receiver@example.com" in message


def test_images_get_content_id_by_list_index_and_missing_entries_are_skipped(tmp_path):
    """TR-026: 画像の Content-ID は一覧の添字で決まり、None の要素は添付しない（添字は保たれる）。"""
    first = tmp_path / "first.png"
    third = tmp_path / "third.png"
    first.write_bytes(PNG_BYTES)
    third.write_bytes(PNG_BYTES)

    _, _, message = _send(body="b", image_list=[str(first), None, str(third)])

    assert "Content-ID: <image_0>" in message
    assert "Content-ID: <image_1>" not in message
    assert "Content-ID: <image_2>" in message
    assert message.count("Content-Type: image/png") == 2


def test_no_images_attaches_only_the_body():
    _, _, message = _send(body="plain")

    assert "Content-ID" not in message


def test_login_failure_propagates_and_nothing_is_sent():
    """ログインに失敗した場合は例外が伝播し、メールは送られず SMTP 接続は閉じられる（#98 Q-016）。"""
    with patch("mail.test_send_mail.smtplib.SMTP") as smtp_cls:
        smtp = smtp_cls.return_value
        smtp.login.side_effect = RuntimeError("auth failed")
        with pytest.raises(RuntimeError, match="auth failed"):
            send_email(CONFIG, "receiver@example.com", body="b")

    smtp.sendmail.assert_not_called()
    smtp.close.assert_called_once()


def test_sendmail_failure_closes_smtp_connection():
    """#98 Q-016: sendmail で例外が発生しても SMTP 接続が必ず閉じられる。"""
    with patch("mail.test_send_mail.smtplib.SMTP") as smtp_cls:
        smtp = smtp_cls.return_value
        smtp.sendmail.side_effect = RuntimeError("send failed")
        with pytest.raises(RuntimeError, match="send failed"):
            send_email(CONFIG, "receiver@example.com", body="b")

    smtp.close.assert_called_once()
