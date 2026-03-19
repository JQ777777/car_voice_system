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

def extract_command_text(raw_text: str):
    """
    只提取“唤醒词后内容”
    """
    if "系统" not in raw_text:
        return None

    return raw_text.split("系统", 1)[-1].strip()


def match_command(cmd_text: str):
    """
    关键词容错匹配
    """
    if not cmd_text:
        return None

    # 去空格
    cmd_text = cmd_text.replace(" ", "")

    # 重复（容错）
    if any(k in cmd_text for k in ["重复", "重", "再来", "再说一遍"]):
        return "REPEAT"

    # 暂停
    if any(k in cmd_text for k in ["暂停", "停一下", "别说了"]):
        return "PAUSE"

    # 继续
    if any(k in cmd_text for k in ["继续", "恢复", "接着说"]):
        return "RESUME"

    # 退出
    if any(k in cmd_text for k in ["退出", "关闭", "结束"]):
        return "EXIT"

    # 回复
    if any(k in cmd_text for k in ["回复", "回消息"]):
        return "REPLY"

    return None

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

            logging.info("原始识别：%s", raw_text)

            # 播放时：只允许“包含唤醒词”的语音进入
            if tts_engine.is_playing and "系统" not in raw_text:
                logging.info("播放中，忽略非唤醒词")
                continue

            # 必须包含唤醒词
            if "系统" not in raw_text:
                logging.info("未检测到唤醒词，忽略")
                continue

            logging.info("🟢 唤醒词触发")

            # 只取“唤醒词后内容”
            cmd_text = extract_command_text(raw_text)

            if not cmd_text:
                logging.warning("唤醒成功，但没有提取到指令内容")
                continue

            logging.info("提取指令内容：%s", cmd_text)

            # 长度限制（只限制指令部分，不是整句）
            # if len(cmd_text) > 6:
            #     logging.warning("指令过长，疑似误识别，忽略")
            #     continue

            # 关键词容错匹配
            command = match_command(cmd_text)

            if not command:
                logging.warning("未匹配到有效指令")
                continue

            logging.info("执行指令：%s", command)

            # 1. 重复
            if command == "REPEAT":
                logging.info("执行：重复（上一条）")

                if tts_engine.last_played_text:
                    repeat_text = tts_engine.last_played_text

                    # 打断（触发回滚）
                    tts_engine.request_interrupt()
                    tts_engine.audio_player.request_interrupt()

                    # 插队
                    tts_engine.speak(repeat_text, priority=True)

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
                tts_engine.stop_all()
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

