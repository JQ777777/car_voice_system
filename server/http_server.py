# http_server.py 消息接收模块
import logging
from flask import Flask, request, jsonify
from threading import Thread

from tts.tts_engine import TTSEngine
from asr.command_parser import CommandASR
from controller.state_machine import StateMachine, SystemState

app = Flask(__name__)
asr_engine = CommandASR(model_path="models/vosk-model-small-cn-0.22")
state_machine = StateMachine()
tts_engine = TTSEngine(state_machine)

# 默认关闭系统
tts_engine.disable()

current_message = None
last_played_message = None

# 用于“恢复播放”的缓存
paused_audio_queue = []
pending_messages = []

reply_target = None
reply_content = None

def extract_command_text(raw_text: str):
    if "系统" not in raw_text:
        return None
    return raw_text.split("系统", 1)[-1].strip()

def match_command(cmd_text: str):
    if not cmd_text:
        return None

    cmd_text = cmd_text.replace(" ", "")

    if any(k in cmd_text for k in ["重复", "重", "再来", "再说一遍"]):
        return "REPEAT"

    if any(k in cmd_text for k in ["暂停", "停一下", "别说了"]):
        return "PAUSE"

    if any(k in cmd_text for k in ["继续", "接着说"]):
        return "RESUME"

    if any(k in cmd_text for k in ["退出", "关闭", "结束"]):
        return "EXIT"

    if any(k in cmd_text for k in ["回复", "回消息"]):
        return "REPLY"

    if any(k in cmd_text for k in ["打开", "开启", "启动"]):
        return "OPEN"

    return None

def command_listener_loop():
    global reply_target, reply_content, paused_audio_queue
    while True:
        try:
            raw_text = asr_engine.listen_text()

            if not raw_text:
                continue

            logging.info("原始识别：%s", raw_text)

            if state_machine.state == SystemState.REPLY_MODE_CONTACT:
                reply_target = raw_text.strip()

                logging.info("识别联系人：%s", reply_target)

                state_machine.set_state(SystemState.REPLY_MODE_CONTENT)

                tts_engine.speak("请说回复内容")
                continue

            if state_machine.state == SystemState.REPLY_MODE_CONTENT:
                reply_content = raw_text.strip()

                logging.info("识别回复内容：%s", reply_content)

                logging.info("发送给 %s：%s", reply_target, reply_content)

                tts_engine.speak(f"已回复{reply_target}", priority=True)

                # 回复完成 → 恢复播放
                logging.info("恢复之前播放队列")

                for _, text in sorted(paused_audio_queue):
                    tts_engine.speak(text)

                paused_audio_queue.clear()

                for msg in pending_messages:
                    tts_engine.speak(msg, priority=False)

                pending_messages.clear()

                reply_target = None
                reply_content = None

                state_machine.set_state(SystemState.WAIT_COMMAND)
                continue

            # 播放中：必须带唤醒词
            if (
                tts_engine.is_playing
                and "系统" not in raw_text
                and state_machine.state not in [
                    SystemState.REPLY_MODE_CONTACT,
                    SystemState.REPLY_MODE_CONTENT
                ]
            ):
                logging.info("播放中，忽略非唤醒词")
                continue

            if "系统" not in raw_text:
                logging.info("未检测到唤醒词，忽略")
                continue

            logging.info("🟢 唤醒词触发")

            cmd_text = extract_command_text(raw_text)

            if not cmd_text:
                continue

            logging.info("提取指令内容：%s", cmd_text)

            command = match_command(cmd_text)

            if not command:
                logging.warning("未匹配到有效指令")
                continue

            logging.info("执行指令：%s", command)

            # 限制reply只能在合理状态触发
            if command == "REPLY" and state_machine.state not in [
                SystemState.MESSAGE_PLAYING,
                SystemState.WAIT_COMMAND
            ]:
                logging.warning("当前状态不允许进入回复模式")
                continue

            # 系统关闭，只允许 OPEN
            if not tts_engine.enabled and command != "OPEN":
                logging.info("系统关闭，仅允许 OPEN 指令")
                continue

            if command == "REPEAT":
                logging.info("执行：重复（上一条）")

                if tts_engine.enabled and tts_engine.last_played_text:
                    repeat_text = tts_engine.last_played_text

                    tts_engine.request_interrupt()
                    tts_engine.audio_player.request_interrupt()
                    tts_engine.audio_player.stop()

                    tts_engine.speak(repeat_text, priority=True)

            elif command == "PAUSE":
                logging.info("执行：暂停")
                tts_engine.pause()

            elif command == "RESUME":
                logging.info("执行：继续播放")
                tts_engine.resume()

            elif command == "EXIT":
                logging.info("执行：关闭系统")

                tts_engine.disable()
                tts_engine.stop_all()

                state_machine.set_state(SystemState.IDLE)

            elif command == "OPEN":
                logging.info("执行：打开系统")

                tts_engine.enable()

                tts_engine.speak("系统已开启", priority=True)

                state_machine.set_state(SystemState.IDLE)

            elif command == "REPLY":
                logging.info("执行：回复模式（打断）")

                # 先打断当前播放和TTS
                tts_engine.request_interrupt()
                tts_engine.audio_player.request_interrupt()

                #tts_engine.interrupt_flag = False

                # 2. 保存当前队列（核心）
                paused_audio_queue = []

                current_item = tts_engine.audio_player.current_item
                if current_item:
                    try:
                        _, timestamp, _, text, _, _ = current_item
                    except Exception:
                        logging.warning("current_item结构异常，跳过")
                
                    paused_audio_queue.append((timestamp, text))

                while not tts_engine.audio_player.queue.empty():
                    try:
                        item = tts_engine.audio_player.queue.get_nowait()
                        _, timestamp, _, text, _, _ = item
                        paused_audio_queue.append((timestamp, text))
                        tts_engine.audio_player.queue.task_done()
                    except:
                        break

                logging.info("缓存未播放消息：%s", paused_audio_queue)

                # 3. 停止当前播放（不清空逻辑）
                tts_engine.audio_player.stop_all()

                # 进入回复模式
                state_machine.set_state(SystemState.REPLY_MODE_CONTACT)

                # 插队提示
                tts_engine.speak("请说联系人", priority=True)

                continue

        except Exception as e:
            logging.error("监听线程异常: %s", e)


# 启动监听线程
Thread(target=command_listener_loop, daemon=True).start()

@app.route("/message", methods=["POST"])
def receive_message():
    data = request.get_json()

    if not data or "sender" not in data or "content" not in data:
        logging.warning("收到格式错误的微信消息: %s", data)
        return jsonify({"status": "error"}), 400

    sender = data["sender"]
    content = data["content"]
    message_text = f"来自 {sender} 的微信消息：{content}"

    if state_machine.state in [
        SystemState.REPLY_MODE_CONTACT,
        SystemState.REPLY_MODE_CONTENT
    ]:
        logging.info("回复中，缓存新消息：%s", message_text)
        pending_messages.append(message_text)
        return jsonify({"status": "queued"})

    logging.info("收到微信消息 | %s: %s", sender, content)

    # 系统关闭直接丢弃
    if not tts_engine.enabled:
        logging.info("系统关闭，忽略消息：%s", message_text)
        return jsonify({"status": "ignored"})

    state_machine.on_message_received()

    Thread(
        target=handle_message_flow,
        args=(message_text,),
        daemon=True
    ).start()

    return jsonify({"status": "ok"})

def handle_message_flow(message_text: str):
    logging.info("进入语音流程 | 当前状态：%s", state_machine.state)

    try:
        if state_machine.state == SystemState.MESSAGE_PLAYING:
            tts_engine.speak(message_text)

        elif state_machine.state == SystemState.WAIT_COMMAND:
            tts_engine.speak("请说出指令")

        elif state_machine.state == SystemState.REPLY_MODE:
            tts_engine.speak("请说出回复内容")
            state_machine.set_state(SystemState.IDLE)

    except Exception as e:
        logging.error("语音流程异常: %s", e)