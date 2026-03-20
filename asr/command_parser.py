# 指令识别模块（Vosk 本地 ASR）
import logging
import queue
import sounddevice as sd
import vosk
import json

class CommandASR:
    def __init__(self, language="zh-CN", model_path="models/vosk-model-small-cn"):
        self.language = language

        # 加载 Vosk 模型
        logging.info("加载 Vosk 模型：%s", model_path)
        self.model = vosk.Model(model_path)
        self.recognizer = vosk.KaldiRecognizer(self.model, 16000)

        # 支持的指令映射表
        self.command_map = {
            "重复": "REPEAT",
            "回复": "REPLY",         
            "退出": "EXIT",
            "暂停": "PAUSE",
            "继续": "RESUME",
            "打开": "OPEN"
        }

        logging.info("本地 ASR 指令识别模块初始化完成")

    def listen_text(self, timeout=15):
        """
        监听用户语音并识别指令，返回指令字符串或 None
        """
        logging.info("开始监听语音指令（Vosk）...")

        # 定义采样参数
        samplerate = 16000
        duration = timeout  # 最大监听时间
        q = queue.Queue()

        def callback(indata, frames, time, status):
            """音频回调，将数据放入队列"""
            if status:
                logging.warning(status)
            q.put(bytes(indata))

        try:
            with sd.RawInputStream(samplerate=samplerate, blocksize=8000, dtype='int16',
                                   channels=1, callback=callback):
                logging.info("请开始说话...")
                import time
                start_time = time.time()
                text = None

                while True:
                    if time.time() - start_time > duration:
                        logging.warning("超时未检测到语音")
                        break

                    if not q.empty():
                        data = q.get()
                        if self.recognizer.AcceptWaveform(data):
                            result = json.loads(self.recognizer.Result())
                            text = result.get("text", "")
                            if text:
                                logging.info("识别到语音内容：%s", text)
                                return text # 直接返回原始文本
        except Exception as e:
            logging.error("本地 ASR 监听失败: %s", e)

        return None
    
    # 指令解析
    def parse_command(self, text: str):
        """
        从文本中解析指令
        """
        if "重复" in text:
            return "REPEAT"
        elif "回复" in text:
            return "REPLY"
        elif "退出" in text:
            return "EXIT"
        elif "暂停" in text:
            command = "PAUSE"
        elif "继续" in text:
            command = "RESUME"
        elif "打开" in text:
            command = "OPEN"
        return None

    def _match_command(self, text: str):
        """将识别文本映射为系统指令"""
        for keyword, command in self.command_map.items():
            if keyword in text:
                logging.info("匹配到指令：%s", command)
                return command

        logging.warning("未匹配到有效指令")
        return None
