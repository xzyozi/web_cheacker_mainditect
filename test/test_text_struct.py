import pytest

from text_struct.text_struct import _is_safe_http_url, generate_html


class TestIsSafeHttpUrl:
    """_is_safe_http_url のユニットテスト。"""

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com",
            "https://example.com/path?a=1&b=2#frag",
            "HTTPS://EXAMPLE.COM/Page",
            "  https://example.com/trimmed  ",
            "http://localhost:8080/status",
            "http://[::1]:8000/",
        ],
    )
    def test_accepts_valid_http_https_urls(self, url: str) -> None:
        assert _is_safe_http_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "JAVASCRIPT:alert(1)",
            "  javascript:alert(1)",
            "java\tscript:alert(1)",
            "java\nscript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
            "file:///etc/passwd",
            "/relative/path",
            "relative/path",
            "//evil.example.com/path",
            "http:example.com",
            "https://",
            "http:///",
            "http://user@",
            "http://[invalid",
            "https://example.com/\x00evil",
            "",
            "   ",
            None,
            123,
        ],
    )
    def test_rejects_unsafe_or_invalid_urls(self, url: object) -> None:
        assert _is_safe_http_url(url) is False


class TestGenerateHtml:
    """generate_html のリンク生成・エスケープ・無害化テスト。"""

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/news",
            "https://example.com/updates?page=1",
        ],
    )
    def test_valid_http_https_urls_render_anchor_href(self, url: str) -> None:
        html_output = generate_html([url], [None])

        assert f'<a href="{url}" target="_blank">リンクを開く</a>' in html_output
        assert f'<p>"{url}"</p>' in html_output
        assert "<p>(スクリーンショット取得失敗)</p>" in html_output

    def test_trimmed_valid_url_renders_clean_href(self) -> None:
        html_output = generate_html(["  https://example.com/clean  "], ["shot.png"])

        assert '<a href="https://example.com/clean" target="_blank">リンクを開く</a>' in html_output
        assert '<img src="cid:image_0" style="max-width:500px;">' in html_output

    def test_html_special_characters_are_autoescaped(self) -> None:
        url = 'https://example.com/search?q=<script>alert(1)</script>&x="quote"'
        html_output = generate_html([url], [None])

        assert "<script>" not in html_output
        assert "&lt;script&gt;" in html_output
        assert "&amp;x=" in html_output
        assert "&#34;" in html_output or "&quot;" in html_output
        assert '<a href="https://example.com/search?q=' in html_output

    @pytest.mark.parametrize(
        "unsafe_url",
        [
            "javascript:alert(1)",
            "JAVASCRIPT:alert(1)",
            "java\tscript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
            "file:///etc/passwd",
            "/relative/path",
            "relative/path.html",
            "//evil.example.com/phish",
            "http:example.com",
            "https://",
        ],
    )
    def test_unsafe_or_non_http_urls_do_not_render_href(self, unsafe_url: str) -> None:
        html_output = generate_html([unsafe_url], [None])

        assert "href=" not in html_output
        assert "<a " not in html_output
        assert "<script>" not in html_output

    def test_unsafe_url_with_html_special_chars_is_escaped_plain_text(self) -> None:
        unsafe_url = 'javascript:alert("<script>&1")'
        html_output = generate_html([unsafe_url], [None])

        assert "href=" not in html_output
        assert "<a " not in html_output
        assert "<script>" not in html_output
        assert "&lt;script&gt;&amp;1" in html_output

    def test_mixed_safe_and_unsafe_urls_only_links_safe_urls(self) -> None:
        urls = [
            "https://safe.example.com/1",
            "javascript:alert(1)",
            "http://safe.example.com/2",
            "data:text/plain,hello",
        ]
        images = ["img1.png", None, "img2.png", None]

        html_output = generate_html(urls, images)

        assert '<a href="https://safe.example.com/1" target="_blank">リンクを開く</a>' in html_output
        assert '<a href="http://safe.example.com/2" target="_blank">リンクを開く</a>' in html_output
        assert 'href="javascript:' not in html_output
        assert 'href="data:' not in html_output
        assert html_output.count("<a ") == 2
        assert '<p>"javascript:alert(1)"</p>' in html_output
        assert '<p>"data:text/plain,hello"</p>' in html_output
