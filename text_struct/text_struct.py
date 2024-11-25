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
        notification += f"\n| - {url}" + " " * (47 - len(url)) + "|"

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

if __name__ == "__main__":
# テスト用のURLリスト
    urls = ["https://example.com/page1", "https://example.com/page2", "https://example.com/page3"]

    # 通知を生成して表示
    print(generate_notification(urls))


    output = """

    """

    print(output)