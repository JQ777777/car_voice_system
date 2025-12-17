# 语音合成模块（Edge TTS）
import asyncio
import edge_tts
import os
import logging


class TTSEngine:
    def __init__(self, voice="zh-CN-XiaoxiaoNeural"):
        self.voice = voice
        self.output_file = "data/audio/tts_output.mp3"

        # 确保音频输出目录存在
        os.makedirs("data/audio", exist_ok=True)

        logging.info("TTS 引擎初始化完成，使用语音模型：%s", self.voice)

    def speak(self, text: str):
        """
        将文本转换为语音并播放
        """
        logging.info("开始语音合成：%s", text)

        try:
            asyncio.run(self._speak_async(text))
            logging.info("语音合成完成，音频文件已生成：%s", self.output_file)
        except Exception:
            logging.error("语音合成失败", exc_info=True)
            return

        # 播放音频
        try:
            if os.name == "nt":
                os.system(f'start {self.output_file}')
            else:
                os.system(f'mpg123 {self.output_file}')
            logging.info("语音播放完成")
        except Exception:
            logging.error("语音播放失败", exc_info=True)

    # 异步合成
    async def _speak_async(self, text: str):
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(self.output_file)
