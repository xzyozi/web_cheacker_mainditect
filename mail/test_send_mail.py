import smtplib
import ssl
import getpass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import yaml
# from . import my_gmail_account as gmail


def get_password():
    # パスワードの取得（安全な方法を選択することが重要）
    return getpass.getpass("Enter your email password: ")

def send_email(config_file,
               receiver_email,               
               body, 
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
    message.attach(MIMEText(body, "plain"))

    # SMTPサーバーの設定
    smtp_server = smtp_server
    port = port

    # SMTPサーバーへの接続とセキュアな通信の確立
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
        # ログイン
        
        server.login(config_file["gmail"]["account"], config_file["gmail"]["password"])

        # メールの送信
        server.sendmail(config_file["gmail"]["account"], receiver_email, message.as_string())

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
