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
            "回复": "REPLY",
            "忽略": "IGNORE",
            "下一条": "NEXT",
            "重复": "REPEAT",
            "退出": "EXIT"
        }

        logging.info("本地 ASR 指令识别模块初始化完成")

    def listen_command(self, timeout=15):
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
                                return self._match_command(text)
        except Exception as e:
            logging.error("本地 ASR 监听失败: %s", e)

        return None

    def _match_command(self, text: str):
        """将识别文本映射为系统指令"""
        for keyword, command in self.command_map.items():
            if keyword in text:
                logging.info("匹配到指令：%s", command)
                return command

        logging.warning("未匹配到有效指令")
        return None
