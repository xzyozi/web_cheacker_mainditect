from itertools import zip_longest
from urllib.parse import urlparse

import jinja2

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


def _is_safe_http_url(url: object) -> bool:
    """http / https スキームと有効なホストを持つ安全な URL かを判定する。"""
    if not isinstance(url, str):
        return False

    candidate = url.strip()
    if not candidate:
        return False

    # 制御文字を含む URL はブラウザ側のスキーム解釈の揺れを防ぐため拒否する
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
        return False

    try:
        parsed = urlparse(candidate)
        hostname = parsed.hostname
    except ValueError:
        return False

    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
        return False
    if not parsed.netloc or not hostname or not hostname.strip():
        return False

    return True


def generate_notification(urls: list):
    notification = """
 _________________________________________________
/                                                  \\
| New updates available!                           |
|                                                  |
| Please access the following URLs to check        |
| for the latest information:                      |
"""
    for url in urls:
        notification += f"\n| - {url}" + " " * (90 - len(url)) + "|"

    notification += "\n\\_________________________________________________/\n"
    notification += "       \\\\\n"  # ここでバックスラッシュをエスケープし、末尾のバックスラッシュを二重化
    notification += "        \\\\\n"  # 同様にバックスラッシュをエスケープし、末尾のバックスラッシュを二重化
    notification += "         \\\\\n"  # 同様にバックスラッシュをエスケープし、末尾のバックスラッシュを二重化
    notification += "                                  .::::.\n"
    notification += "                                .::::::::.\n"
    notification += "                               :::::::::::\n"
    notification += "                            ..:::::::::::'\n"
    notification += "                         '::::::::::::'\n"
    notification += "                           .::::::::::\n"
    notification += "                      '::::::::::::::..\n"
    notification += "                           ..::::::::::::.\n"
    notification += "                         ``::::::::::::::::\n"
    notification += "                          ::::``:::::::::'        .:::.\n"
    notification += "                         ::::'   ':::::'       .::::::::.\n"
    notification += "                       .::::'      ::::     .:::::::'::::.\n"
    notification += "                      .:::'       :::::  .:::::::::' ':::::.\n"
    notification += "                     .::'        :::::.:::::::::'      ':::::.\n"
    notification += "                 ...:::          :::::::::::'          ::::::..\n"
    notification += "                ```` ':.         '::::::::::            ::::::::..\n"
    notification += "                                   ':::::::::             :::::::::\n"
    notification += "                                     ':::::::.             :::::::::\n"
    notification += "                                        :::::...           ::::::::::\n"
    notification += "                                       ':::::::::.        .:::::::::'\n"
    notification += "                                        .::::::::::       .:::::::'\n"
    notification += "                                           ..::::::::    .:::::::'\n"
    notification += "                                         ``:::::::::    ::::::''\n"
    notification += "                                            ``:::::'   .::''''\n"
    notification += "                                               `````\n"

    return notification


def generate_html(url_list, image_list):
    """
    指定されたURLと画像リストを元にHTMLを生成する。
    画像リストの要素がNoneの場合は、画像なしでHTMLを生成する。
    """
    items = []
    # image_list内のNoneでないパスに対応するcidを生成
    cids = {path: f"image_{i}" for i, path in enumerate(image_list) if path}

    for url, image_path in zip_longest(url_list, image_list):
        safe_url = url.strip() if isinstance(url, str) and _is_safe_http_url(url) else None
        item = {"url": url, "safe_url": safe_url, "cid": None}
        if image_path and image_path in cids:
            item["cid"] = cids[image_path]
        items.append(item)

    # 画像をBase64エンコード
    # images_base64 = []
    # for image_path in image_list:

    #     with open(image_path, "rb") as img_file:
    #         # ファイル拡張子を判定し、適切なMIMEタイプを設定
    #         file_ext = os.path.splitext(image_path)[1].lower()

    #         mime_type = "image/png" if file_ext == ".png" else "image/jpeg"
    #         encoded_image = str(base64.b64encode(img_file.read()))
    #         images_base64.append(f"data:{mime_type};base64,{encoded_image}")

    # Jinja2テンプレート
    template = jinja2.Environment(autoescape=True).from_string("""
    <html>
        <body>
            <h2>更新ページ一覧</h2>

            <ul>
            {% for item in items %}
                <li>
                    <p>"{{ item.url }}"</p>
                    {% if item.safe_url %}
                    <a href="{{ item.safe_url }}" target="_blank">リンクを開く</a><br>
                    {% endif %}
                    {% if item.cid %}
                    <img src="cid:{{ item.cid }}" style="max-width:500px;">
                    {% else %}
                    <p>(スクリーンショット取得失敗)</p>
                    {% endif %}
                </li>
            {% endfor %}
            </ul>
        </body>
    </html>
    """)

    html_content = template.render(items=items)

    # URLとBase64画像のペアをテンプレートに渡す
    # html_content = template.render(items=zip(url_list, images_base64))
    # html_content = template.render(items=zip(url_list, [f"image_{i}" for i in range(len(image_list))]))

    return html_content


if __name__ == "__main__":
    # テスト用のURLリスト
    urls = ["https://example.com/page1", "https://example.com/page2", "https://example.com/page3"]

    # 通知を生成して表示
    print(generate_notification(urls))

    output = """

    """

    print(output)
