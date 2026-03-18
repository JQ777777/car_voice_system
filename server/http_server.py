# http_server.py 消息接收模块
import logging
import time
from flask import Flask, request, jsonify
from threading import Thread

from tts.tts_engine import TTSEngine
from asr.command_parser import CommandASR
from controller.state_machine import StateMachine, SystemState

app = Flask(__name__)
asr_engine = CommandASR(model_path="models/vosk-model-small-cn-0.22")
state_machine = StateMachine()
tts_engine = TTSEngine(state_machine)

current_message = None          # 当前消息
last_played_message = None      # 上一条已播放完成的消息
message_queue = []              # 消息队列（逻辑层）

def command_listener_loop():
    """
    持续监听用户语音指令（支持打断 + 唤醒词）
    """
    global current_message, last_played_message

    while True:
        try:
            raw_text = asr_engine.listen_text()

            if not raw_text:
                continue

            logging.info("🎤 原始识别：%s", raw_text)

            # 播放时屏蔽非唤醒词（防自我识别）
            if tts_engine.is_playing and "系统" not in raw_text:
                logging.info("播放中，忽略非唤醒词")
                continue

            # 唤醒词检测
            if "系统" not in raw_text:
                logging.info("未检测到唤醒词，忽略")
                continue

            logging.info("🟢 唤醒词触发")

            # 防误触（过长语句过滤）
            if len(raw_text) > 10:
                logging.info("语句过长，疑似误识别，忽略")
                continue

            # 提取指令
            command = asr_engine.parse_command(raw_text)

            if not command:
                logging.warning("唤醒成功，但未匹配指令")
                continue

            logging.info("执行指令：%s", command)

            # 1. 重复
            if command == "REPEAT":
                logging.info("执行：重复上一条")

                if last_played_message:
                    tts_engine.speak(last_played_message)

                continue

            # 2. 暂停
            elif command == "PAUSE":
                logging.info("执行：暂停")
                tts_engine.pause()
                continue

            # 3. 继续
            elif command == "RESUME":
                logging.info("执行：继续播放")
                tts_engine.resume()
                continue

            # 4. 退出（停止一切）
            elif command == "EXIT":
                logging.info("执行：退出")
                tts_engine.stop()
                state_machine.set_state(SystemState.IDLE)
                continue

            # 5. 回复（进入模式）
            elif command == "REPLY":
                logging.info("执行：回复模式")

                tts_engine.stop()  # 可以中断
                state_machine.set_state(SystemState.REPLY_MODE)

                tts_engine.speak("请说出回复内容")
                continue

        except Exception as e:
            logging.error("监听线程异常: %s", e)

# 🔥 启动监听线程（只启动一次）
Thread(
    target=command_listener_loop,
    daemon=True
).start()

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
    message_text = f"来自 {sender} 的微信消息：{content}"

    logging.info("收到微信消息 | %s: %s", sender, content)

    # 状态：收到消息
    state_machine.on_message_received()

    # 启用后台线程处理语音流程
    Thread(
        target=handle_message_flow,
        args=(message_text,),
        daemon=True
    ).start()

    return jsonify({"status": "ok"})

# 语音交互主流程，由状态机驱动
def handle_message_flow(message_text: str):
    logging.info("进入语音流程 | 当前状态：%s", state_machine.state)

    try:
        # 播放消息
        if state_machine.state == SystemState.MESSAGE_PLAYING:
            tts_engine.speak(message_text)

        # 等待指令（只提示，不阻塞）
        elif state_machine.state == SystemState.WAIT_COMMAND:
            tts_engine.speak("请说出指令")

        # 回复模式
        elif state_machine.state == SystemState.REPLY_MODE:
            tts_engine.speak("请说出回复内容")
            state_machine.set_state(SystemState.IDLE)

    except Exception as e:
        logging.error("语音流程异常: %s", e)

