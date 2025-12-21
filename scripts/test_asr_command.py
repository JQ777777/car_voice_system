# 测试语音识别模块
import logging
from asr.command_parser import CommandASR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

asr = CommandASR()

while True:
    cmd = asr.listen_command()
    if cmd:
        print(f"👉 识别到指令: {cmd}")
        if cmd == "EXIT":
            break

