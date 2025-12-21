# run.py 系统主入口（只负责启动）
from server.http_server import app
from common import setup_logger
import logging
from waitress import serve

def main():
    setup_logger()
    logging.info("🚗 车载语音交互系统启动中...")
    
    logging.info("正在启动 HTTP 服务 (端口: 5001)...")
    
    # waitress 启动 HTTP 服务
    serve(
        app,                    # Flask 应用
        host='0.0.0.0',        # 监听所有地址
        port=5001,             # 端口
        threads=4,             # 线程数
        channel_timeout=60     # 超时时间
    )

if __name__ == "__main__":
    main()
