# 测试脚本：模拟微信端发送消息
import requests
import logging

def main():
    messages = [
        {"sender": "小张", "content": "今晚一起吃饭吗？"},
        {"sender": "小李", "content": "明天早上开会别忘了"},
        {"sender": "小王", "content": "帮我看看这个代码"},
        {"sender": "小张", "content": "好的，没问题"}
    ]

    url = "http://127.0.0.1:5001/message"

    for msg in messages:
        resp = requests.post(url, json=msg)
        print(resp.json())

if __name__ == "__main__":
    main()
