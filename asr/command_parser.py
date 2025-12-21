#指令识别模块
import logging
import speech_recognition as sr # 语音识别库

# 语音指令识别模块
class CommandASR:
    def __init__(self, language="zh-CN"):
        self.language = language
        self.recognizer = sr.Recognizer() # 创建语音识别器实例
        self.microphone = sr.Microphone() # 获取系统麦克风

        # 支持的指令映射表
        self.command_map = {
            "回复": "REPLY",
            "忽略": "IGNORE",
            "下一条": "NEXT",
            "重复": "REPEAT",
            "退出": "EXIT"
        }

        logging.info("ASR 指令识别模块初始化完成")

    # 监听用户语音并识别指令，return 指令字符串 或 None
    def listen_command(self, timeout=5):
        logging.info("开始监听语音指令...")

        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=3
                )
            except sr.WaitTimeoutError:
                logging.warning("未检测到语音输入")
                return None

        try:
            text = self.recognizer.recognize_google(audio, language=self.language)
            logging.info("识别到语音内容：%s", text)

            return self._match_command(text)

        except sr.UnknownValueError:
            logging.warning("无法识别语音内容")
        except sr.RequestError as e:
            logging.error("ASR 服务请求失败: %s", e)

        return None

    # 将识别文本映射为系统指令
    def _match_command(self, text: str):
        for keyword, command in self.command_map.items():
            if keyword in text:
                logging.info("匹配到指令：%s", command)
                return command

        logging.warning("未匹配到有效指令")
        return None
