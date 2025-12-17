# http_server.py 消息接收模块
import logging
from flask import Flask, request, jsonify

from tts.tts_engine import TTSEngine

app = Flask(__name__)
tts_engine = TTSEngine()

# 微信消息接收
@app.route("/message", methods=["POST"])
def receive_message():
    """
    数据格式：
    {
        "sender": "小张",
        "content": "今晚一起吃饭吗？"
    }
    """
    data = request.get_json()

    if not data or "sender" not in data or "content" not in data:
        logging.warning("收到格式错误的微信消息: %s", data)
        return jsonify({"status": "error", "msg": "Invalid message format"}), 400

    sender = data["sender"]
    content = data["content"]

    logging.info("收到微信消息 | %s: %s", sender, content)

    # 拼接播报文本
    speak_text = f"来自 {sender} 的微信消息：{content}"

    try:
        tts_engine.speak(speak_text)
        logging.info("TTS 播报完成")
    except Exception as e:
        logging.error("TTS 播报失败", exc_info=True)
        return jsonify({"status": "error", "msg": "TTS failed"}), 500

    return jsonify({"status": "ok"})
