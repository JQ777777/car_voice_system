# test_waitress.py - 快速验证 waitress 是否工作
from flask import Flask, jsonify
from waitress import serve
import logging

app = Flask(__name__)

@app.route('/')
def home():
    return '🚗 车载语音系统 Waitress 测试'

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "server": "waitress"})

@app.route('/message', methods=['POST'])
def message():
    return jsonify({"status": "ok", "msg": "消息已收到"})

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("正在启动 Waitress 服务器...")
    
    # 启动 waitress
    serve(
        app,
        host='0.0.0.0',
        port=5001,
        threads=4
    )