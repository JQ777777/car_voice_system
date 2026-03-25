# http_server.py 消息接收模块
import logging
import json
import requests
import time
from flask import Flask, request, jsonify, Response
from threading import Thread

from tts.tts_engine import TTSEngine
from asr.command_parser import CommandASR
from controller.state_machine import StateMachine, SystemState
from pypinyin import lazy_pinyin
from rapidfuzz import fuzz

app = Flask(__name__)
@app.after_request
def add_ngrok_skip_header(response):
    response.headers['ngrok-skip-browser-warning'] = 'true'
    return response

asr_engine = CommandASR(model_path="models/vosk-model-small-cn-0.22")
state_machine = StateMachine()
tts_engine = TTSEngine(state_machine, mode="edge")

APP_ID = "cli_a94a1608a4f9dbb4"
APP_SECRET = "suqqFJqr1BRmv6s0UsPSndFiFqcKnhE8"

tenant_access_token = None
token_time = 0
TOKEN_EXPIRE = 3600
user_cache = {}
CACHE_EXPIRE = 3600

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

def add_natural_punctuation(text):
    """
    为语音识别文本添加自然标点
    """
    if not text:
        return text
    
    # 常见的疑问词
    question_words = ["吗", "呢", "吧", "啊", "呀", "怎么", "什么", "为什么", "谁", "哪", "几", "多少"]
    
    # 常见的感叹词
    exclamation_words = ["啊", "呀", "哇", "啦", "吧", "呢", "哎", "哦", "哈"]
    
    # 检查是否是疑问句
    is_question = False
    for word in question_words:
        if text.endswith(word) or word in text.split()[-2:]:
            is_question = True
            break
    
    # 检查是否是感叹句
    is_exclamation = False
    if text.endswith("！") or text.endswith("!"):
        is_exclamation = True
    else:
        for word in exclamation_words:
            if text.endswith(word) and len(text) > len(word):
                is_exclamation = True
                break
    
    # 添加句号
    if not (text.endswith("。") or text.endswith("？") or text.endswith("！") or 
            text.endswith(".") or text.endswith("?") or text.endswith("!")):
        if is_question:
            text += "？"
        elif is_exclamation:
            text += "！"
        else:
            text += "。"
    
    return text

def command_listener_loop():
    global reply_target, reply_content, paused_audio_queue
    while True:
        try:
            raw_text = asr_engine.listen_text()

            if not raw_text:
                continue

            logging.info("原始识别：%s", raw_text)

            if state_machine.state == SystemState.REPLY_MODE_CONTACT:
                # ... 联系人识别代码保持不变
                recognized_name = raw_text.strip()
                logging.info("识别到联系人（原始）: %s", recognized_name)
                
                matched_user = match_user_by_text(recognized_name)
                
                if matched_user:
                    reply_target = matched_user["name"]
                    logging.info("✅ 匹配到联系人: %s (原识别: %s)", reply_target, recognized_name)
                else:
                    reply_target = recognized_name
                    logging.warning("❌ 未匹配到联系人，使用原始识别: %s", reply_target)

                state_machine.set_state(SystemState.REPLY_MODE_CONTENT)
                tts_engine.speak("请说回复内容")
                continue

            if state_machine.state == SystemState.REPLY_MODE_CONTENT:
                # 获取识别文本
                recognized_content = raw_text.strip()
                
                # 清理多余空格，但保留基本结构
                content = recognized_content.replace(" ", "")
                
                # 添加自然标点
                content = add_natural_punctuation(content)
                
                reply_content = content
                
                logging.info("识别回复内容（原始）: %s", recognized_content)
                logging.info("识别回复内容（处理后）: %s", reply_content)
                logging.info("发送给 %s：%s", reply_target, reply_content)

                # 查找回复目标的 open_id
                target_open_id = None
                for uid, info in user_cache.items():
                    if info["name"] == reply_target:
                        target_open_id = info.get("open_id")
                        break
                
                if target_open_id:
                    # 发送消息
                    success = send_feishu_message(target_open_id, reply_content)
                    if success:
                        tts_engine.speak(f"已回复{reply_target}", priority=True)
                    else:
                        tts_engine.speak(f"回复{reply_target}失败", priority=True)
                else:
                    logging.error("未找到目标用户的 open_id: %s", reply_target)
                    tts_engine.speak(f"未找到{reply_target}的联系方式", priority=True)

                # 恢复播放队列
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
                SystemState.WAIT_COMMAND,
                SystemState.IDLE
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

                    #tts_engine.request_interrupt()
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

                state_machine.turn_off()

            elif command == "OPEN":
                logging.info("执行：打开系统")

                tts_engine.enable()

                tts_engine.speak("系统已开启", priority=True)

                state_machine.set_state(SystemState.IDLE)

            elif command == "REPLY":
                logging.info("执行：回复模式（打断）")

                if tts_engine.is_playing:
                    logging.info("执行打断（正在播放）")

                    tts_engine.request_interrupt()
                    tts_engine.audio_player.request_interrupt()
                else:
                    logging.info("系统空闲，无需打断")


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

def handle_message_flow(message_text: str):
    logging.info("进入语音流程 | 当前状态：%s", state_machine.state)

    try:
        if state_machine.state == SystemState.MESSAGE_PLAYING:
            tts_engine.speak(message_text)

        # elif state_machine.state == SystemState.WAIT_COMMAND:
        #     tts_engine.speak("请说出指令")

        elif state_machine.state == SystemState.REPLY_MODE:
            tts_engine.speak("请说出回复内容")
            state_machine.set_state(SystemState.IDLE)

    except Exception as e:
        logging.error("语音流程异常: %s", e)

def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"

    data = {
        "app_id": APP_ID,
        "app_secret": APP_SECRET
    }

    resp = requests.post(url, json=data).json()

    logging.info("获取token返回: %s", resp)

    return resp.get("tenant_access_token")

def ensure_token():
    global tenant_access_token, token_time

    if not tenant_access_token or time.time() - token_time > TOKEN_EXPIRE:
        logging.info("获取/刷新 tenant_access_token")
        tenant_access_token = get_tenant_access_token()
        token_time = time.time()

def get_user_name(open_id):
    ensure_token()
    url = "https://open.feishu.cn/open-apis/contact/v3/users/" + open_id

    headers = {
        "Authorization": f"Bearer {tenant_access_token}"
    }

    resp = requests.get(url, headers=headers).json()
    
    # 添加调试：打印完整用户信息
    logging.info("飞书用户接口返回: %s", json.dumps(resp, ensure_ascii=False, indent=2))

    if resp.get("code") != 0:
        logging.error("获取用户失败: %s", resp)
        return None

    user_info = resp.get("data", {}).get("user", {})
    
    # 打印所有字段的值
    logging.info("用户信息所有字段: %s", list(user_info.keys()))
    
    # 尝试多种可能的姓名字段
    user_name = user_info.get("nickname")
    if user_name:
        logging.info("使用昵称: %s", user_name)
    
    if not user_name:
        user_name = user_info.get("en_name")
        if user_name:
            logging.info("使用英文名: %s", user_name)
    
    if not user_name:
        user_name = user_info.get("employee_name")
        if user_name:
            logging.info("使用员工姓名: %s", user_name)
    
    if not user_name:
        user_name = user_info.get("name")
        if user_name:
            logging.info("使用中文名: %s", user_name)
    
    if not user_name:
        user_name = user_info.get("display_name")
        if user_name:
            logging.info("使用显示名称: %s", user_name)

    if not user_name:
        logging.error("所有姓名字段均为空: %s", resp)
        return None

    logging.info("最终获取到用户姓名: %s", user_name)
    return user_name

def get_candidate_users():
    return [
        {
            "open_id": uid,
            "name": info["name"],
            "pinyin": info["pinyin"]
        }
        for uid, info in user_cache.items()
    ]

def match_user_by_text(text):
    from rapidfuzz import fuzz
    from rapidfuzz.fuzz import partial_ratio
    
    candidates = get_candidate_users()
    
    if not candidates:
        logging.warning("⚠️ 候选用户列表为空，无法匹配")
        return None

    best_user = None
    best_score = 0
    
    # 处理语音识别结果
    text_pinyin = " ".join(lazy_pinyin(text))
    text_clean = text.strip().lower()
    
    logging.info("🔍 开始匹配用户 - 输入: '%s' (拼音: '%s')", text, text_pinyin)
    
    for user in candidates:
        # 获取用户的拼音首字母（用于匹配昵称）
        user_pinyin_list = lazy_pinyin(user["name"])
        user_first_pinyin = user_pinyin_list[0] if user_pinyin_list else ""
        
        # 多种匹配方式
        name_score = fuzz.ratio(text_clean, user["name"].lower())
        pinyin_score = fuzz.ratio(text_pinyin, user["pinyin"])
        partial_name_score = partial_ratio(text_clean, user["name"].lower())
        
        # 特殊处理：如果输入是"小哥"，用户是"小何"
        # 检查拼音相似度
        pinyin_similarity = fuzz.ratio(text_pinyin, user["pinyin"])
        
        # 如果输入是2个字，检查是否匹配用户名的前两个字
        name_prefix_match = 0
        if len(text_clean) <= len(user["name"]):
            prefix = user["name"][:len(text_clean)]
            prefix_score = fuzz.ratio(text_clean, prefix)
            if prefix_score > name_prefix_match:
                name_prefix_match = prefix_score
        
        # 综合评分（提高拼音匹配的权重）
        score = max(
            0.3 * name_score + 0.5 * pinyin_score + 0.2 * partial_name_score,
            name_prefix_match
        )
        
        logging.info("  - 用户: %s (拼音: %s)", user["name"], user["pinyin"])
        logging.info("    名称匹配: %.2f%%, 拼音匹配: %.2f%%, 部分匹配: %.2f%%, 前缀匹配: %.2f%%, 综合: %.2f%%", 
                   name_score, pinyin_score, partial_name_score, name_prefix_match, score)
        
        if score > best_score:
            best_score = score
            best_user = user

    # 降低阈值到45，因为"小何"和"小哥"拼音相似度较高
    if best_score < 45:
        logging.warning("❌ 最佳匹配度 %.2f%% 低于阈值 45%%，匹配失败", best_score)
        return None

    logging.info("✅ 最佳匹配: %s (匹配度: %.2f%%)", best_user["name"], best_score)
    return best_user


def process_feishu_event(data):
    current_time = time.time()
    try:
        logging.info("🚀 开始处理飞书事件")
        
        # 打印完整事件数据
        logging.info("完整事件数据: %s", json.dumps(data, ensure_ascii=False, indent=2))
        
        header = data.get("header", {})
        event = data.get("event", {})
        
        event_type = header.get("event_type")
        logging.info("📌 事件类型: %s", event_type)
        
        # 检查是否是消息事件
        if event_type != "im.message.receive_v1":
            logging.info("❌ 不是消息事件，忽略 (事件类型: %s)", event_type)
            return
        
        logging.info("✅ 是消息事件，继续处理")
        
        # 提取消息信息
        message = event.get("message", {})
        sender = event.get("sender", {})
        
        logging.info("📨 消息对象: %s", json.dumps(message, ensure_ascii=False, indent=2))
        logging.info("👤 发送者对象: %s", json.dumps(sender, ensure_ascii=False, indent=2))
        
        # 提取消息内容
        content_str = message.get("content", "{}")
        logging.info("原始消息内容字符串: %s", content_str)
        
        try:
            content_dict = json.loads(content_str)
            logging.info("解析后的消息内容: %s", json.dumps(content_dict, ensure_ascii=False))
        except json.JSONDecodeError as e:
            logging.error("消息内容JSON解析失败: %s", e)
            return
        
        # 提取文本
        text = content_dict.get("text", "")
        logging.info("📝 原始消息文本: %s", text)
        
        # 清理文本
        import re
        text_original = text
        
        # 去掉所有 @mention
        text = re.sub(r'@\S+', '', text)
        logging.info("清理@mention后: %s", text)
        
        # 去掉 mentions
        mentions = content_dict.get("mentions", [])
        logging.info("Mentions数量: %d", len(mentions))
        for mention in mentions:
            key = mention.get("key")
            if key:
                text = text.replace(key, "")
                logging.info("移除mention key: %s", key)
        
        # 清理空格
        text = re.sub(r'\s+', ' ', text).strip()
        logging.info("最终清理后的文本: %s", text)
        
        # 如果没有内容，忽略
        if not text:
            logging.info("⚠️ 消息内容为空，忽略")
            return
        
        # 获取发送者信息
        sender_id = sender.get("sender_id", {}).get("open_id")
        logging.info("发送者 open_id: %s", sender_id)
        
        if not sender_id:
            logging.warning("⚠️ 无法获取发送者ID")
            user_name = "未知用户"
        else:
            # 获取用户名
            if sender_id in user_cache:
                cached_data = user_cache[sender_id]
                user_name = cached_data["name"]
                last_seen = cached_data["last_seen"]
                logging.info("从缓存获取用户名: %s (缓存时间: %s)", user_name, last_seen)
                
                if current_time - last_seen > CACHE_EXPIRE:
                    logging.info("缓存过期，重新获取")
                    user_name = get_user_name(sender_id)
                    if user_name:
                        pinyin_name = " ".join(lazy_pinyin(user_name))
                        user_cache[sender_id] = {
                            "name": user_name,
                            "pinyin": pinyin_name,
                            "open_id": sender_id,
                            "last_seen": current_time
                        }
                        logging.info("更新缓存: %s -> %s", sender_id, user_name)
            else:
                logging.info("缓存未命中，调用API获取用户名")
                user_name = get_user_name(sender_id)
                if user_name:
                    pinyin_name = " ".join(lazy_pinyin(user_name))
                    user_cache[sender_id] = {
                        "name": user_name,
                        "pinyin": pinyin_name,
                        "open_id": sender_id,
                        "last_seen": current_time
                    }
                    logging.info("新增缓存: %s -> %s", sender_id, user_name)
                else:
                    user_name = "未知用户"
                    logging.warning("无法获取用户名")
        
        # 构建播报文本
        message_text = f"收到{user_name}的消息：{text}"
        logging.info("🎙️ 最终播报文本: %s", message_text)
        
        # 检查系统状态
        logging.info("当前系统状态: %s", state_machine.state)
        logging.info("TTS引擎状态: %s", "启用" if tts_engine.enabled else "关闭")
        
        # 回复模式处理
        if state_machine.state in [
            SystemState.REPLY_MODE_CONTACT,
            SystemState.REPLY_MODE_CONTENT
        ]:
            logging.info("📦 当前在回复模式，消息入队等待处理")
            pending_messages.append(message_text)
            return
        
        # 系统关闭检查
        if not tts_engine.enabled:
            logging.info("🔇 系统已关闭，忽略消息")
            return
        
        # 正常播报
        logging.info("✅ 进入正常播报流程")
        state_machine.on_message_received()
        
        Thread(
            target=handle_message_flow,
            args=(message_text,),
            daemon=True
        ).start()
        
        logging.info("✨ 飞书事件处理完成")
        
    except Exception as e:
        logging.error("飞书处理异常: %s", e, exc_info=True)

def send_feishu_message(open_id, content):
    """
    发送飞书消息到指定用户
    """
    ensure_token()
    
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    
    headers = {
        "Authorization": f"Bearer {tenant_access_token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({
            "text": content
        })
    }
    
    # 添加查询参数，指定接收者类型
    params = {
        "receive_id_type": "open_id"
    }
    
    try:
        resp = requests.post(url, headers=headers, params=params, json=data)
        result = resp.json()
        
        if result.get("code") == 0:
            logging.info("✅ 消息发送成功: %s -> %s", open_id, content)
            return True
        else:
            logging.error("❌ 消息发送失败: %s", result)
            return False
    except Exception as e:
        logging.error("发送消息异常: %s", e)
        return False

@app.route("/feishu", methods=["POST", "GET"])
def feishu_webhook():
    # 获取请求数据
    raw_data = request.get_data(as_text=True)
    
    logging.info("=" * 60)
    logging.info("📨 收到飞书请求")
    logging.info("请求方法: %s", request.method)
    logging.info("原始数据长度: %d", len(raw_data))
    
    # 处理 GET 请求（测试用）
    if request.method == "GET":
        return Response('{"status":"ok"}', mimetype="application/json", status=200)
    
    # 处理挑战验证（必须立即返回）
    if "challenge" in raw_data:
        try:
            data = json.loads(raw_data)
            challenge = data.get("challenge")
            logging.info("🔐 处理URL验证，challenge: %s", challenge)
            # 必须立即返回，不能有任何延迟
            return Response(
                f'{{"challenge":"{challenge}"}}',
                mimetype="application/json",
                status=200
            )
        except Exception as e:
            logging.error("验证处理失败: %s", e)
            return Response('{"code":-1}', mimetype="application/json", status=200)
    
    # 处理普通事件（必须快速返回，避免超时）
    try:
        # 解析数据
        data = json.loads(raw_data)
        
        # 检查事件类型
        header = data.get("header", {})
        event_type = header.get("event_type")
        
        logging.info("✅ 收到事件: %s", event_type)
        
        # 只处理消息事件
        if event_type == "im.message.receive_v1":
            # 异步处理，避免阻塞响应
            Thread(target=process_feishu_event, args=(data,), daemon=True).start()
        else:
            logging.info("忽略非消息事件: %s", event_type)
        
        # 立即返回成功响应（必须在3秒内返回）
        return Response('{"code":0}', mimetype="application/json", status=200)
        
    except json.JSONDecodeError as e:
        logging.error("JSON解析失败: %s", e)
        return Response('{"code":-1}', mimetype="application/json", status=200)
    except Exception as e:
        logging.error("处理事件失败: %s", e, exc_info=True)
        return Response('{"code":-1}', mimetype="application/json", status=200)