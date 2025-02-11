import os
import jinja2
import base64
from itertools import zip_longest

def generate_notification(urls : list):
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
    """
    if len(url_list) != len(image_list):
        # print(f"url_list {len(url_list)} image_list {len(image_list)}") 
        for url, image in zip_longest(url_list, image_list, fillvalue="None"):
            print(f"url {url} image {image}")
        raise ValueError("URLリストと画像リストの長さが一致していません。")

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
    # Jinja2テンプレート
    template = jinja2.Template("""
    <html>
        <body>
            <h2>更新ページ一覧 </h2>
            
            <ul>
            {% for url, cid in items %}
                <li>
                    <p>"{{ url }}"</p>
                    <a href="{{ url }}" target="_blank">リンクを開く</a><br>
                    <img src="cid:{{ cid }}" style="max-width:500px;">
                </li>
            {% endfor %}
            </ul>
        </body>
    </html>
    """)

    # Content-IDリストを生成（image_0, image_1, ...）
    cid_list = [f"image_{i}" for i in range(len(image_list))]
    
    # URLとContent-IDのペアをテンプレートに渡す
    html_content = template.render(items=zip(url_list, cid_list))
    return html_content


    # URLとBase64画像のペアをテンプレートに渡す
    #html_content = template.render(items=zip(url_list, images_base64))
    html_content = template.render(items=zip(url_list, [f"image_{i}" for i in range(len(image_list))]))
    return html_content


if __name__ == "__main__":
# テスト用のURLリスト
    urls = ["https://example.com/page1", "https://example.com/page2", "https://example.com/page3"]

    # 通知を生成して表示
    print(generate_notification(urls))


    output = """

    """

    print(output)