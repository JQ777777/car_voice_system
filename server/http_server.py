# http_server.py 消息接收模块
import logging
import time
from flask import Flask, request, jsonify

from tts.tts_engine import TTSEngine
from asr.command_parser import CommandASR
from controller.state_machine import StateMachine, SystemState

app = Flask(__name__)
tts_engine = TTSEngine()
asr_engine = CommandASR()
state_machine = StateMachine()

current_message = None  # 当前处理的消息

# 微信消息接收
@app.route("/message", methods=["POST"])
def receive_message():
    global current_message
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
    current_message = f"来自 {sender} 的微信消息：{content}"

    logging.info("收到微信消息 | %s: %s", sender, content)

    # 状态：收到消息
    state_machine.on_message_received()

    handle_message_flow()

    return jsonify({"status": "ok"})

# 语音交互主流程，由状态机驱动
def handle_message_flow():
    global current_message

    # MESSAGE_PLAYING
    if state_machine.state == SystemState.MESSAGE_PLAYING:
        tts_engine.speak(current_message)
        state_machine.on_play_finished()

    # WAIT_COMMAND
    if state_machine.state == SystemState.WAIT_COMMAND:
        tts_engine.speak("请说出指令")

        time.sleep(1)

        command = asr_engine.listen_command()
        logging.info("识别到指令：%s", command)

        state_machine.on_command(command)

        # 根据状态机结果继续处理
        if state_machine.state == SystemState.MESSAGE_PLAYING:
            handle_message_flow()

        elif state_machine.state == SystemState.IDLE:
            logging.info("消息已忽略，系统回到空闲状态")

        elif state_machine.state == SystemState.REPLY_MODE:
            tts_engine.speak("请说出回复内容")
            state_machine.set_state(SystemState.IDLE)

