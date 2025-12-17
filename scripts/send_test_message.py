# 测试脚本：模拟微信端发送消息
import logging
import requests


def main():
    logging.info("开始发送测试微信消息")

    url = "http://127.0.0.1:5001/message"

    data = {
        "sender": "小张",
        "content": "今晚一起吃饭吗？"
    }

    try:
        resp = requests.post(url, json=data, timeout=5)
        logging.info("服务器响应状态码：%s", resp.status_code)
        logging.info("服务器返回内容：%s", resp.json())
    except Exception:
        logging.error("发送测试消息失败", exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    main()
