import smtplib
import ssl
import getpass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import yaml
import os
# Gmail認証に必要
# from googleapiclient.discovery import build
# from httplib2                  import Http
# from oauth2client              import file, client, tools


def get_password():
    # パスワードの取得（安全な方法を選択することが重要）
    return getpass.getpass("Enter your email password: ")

def send_email(config_file,
               receiver_email,               
               body,
               body_type = "plain", 
               image_list = [],
               subject = "",
               smtp_server = "smtp.gmail.com",
               port = 465 # port number
               ):
    # メールの構築
    message = MIMEMultipart()
    message["From"] = config_file["gmail"]["account"]
    message["To"] = receiver_email
    message["Subject"] = subject

    # メール本文の追加
    message.attach(MIMEText(body, body_type))

    # 画像を添付
    for i, image_path in enumerate(image_list):
        if not image_path:
            continue
        file_ext = os.path.splitext(image_path)[1].lower()
        ext = file_ext[1:]
        with open(image_path, "rb") as img_file:
            img = MIMEImage(img_file.read(), _subtype=f'{ext}')
            img.add_header("Content-ID", f"<image_{i}>")
            message.attach(img)

    # SMTPサーバーの設定
    smtp_server = smtp_server
    port = port

    # SMTPサーバーへの接続とセキュアな通信の確立
    # context = ssl.create_default_context()
    # with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
    #     # ログイン
        
    #     server.login(config_file["gmail"]["account"], config_file["gmail"]["password"])

    #     # メールの送信
    #     server.sendmail(config_file["gmail"]["account"], receiver_email, message.as_string())

    smtpobj = smtplib.SMTP('smtp.gmail.com', 587)
    smtpobj.ehlo()
    smtpobj.starttls()
    smtpobj.ehlo()
    smtpobj.login(config_file["gmail"]["account"], config_file["gmail"]["password"])
    smtpobj.sendmail(config_file["gmail"]["account"], receiver_email, message.as_string())
    smtpobj.close()

    print("メールが送信されました。")

if __name__ == "__main__":

    receiver_email = "your@gmail.com"
    subject = "テストメール"
    body = """


    moimoi
    """

    config_pass = "mail/mail.yaml"
    with open(config_pass)as f :
        yaml_file = yaml.safe_load(f)

    send_email(yaml_file, receiver_email, subject, body)
