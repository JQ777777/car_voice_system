# 语音合成模块（Edge TTS）
import asyncio
import edge_tts
import os
import logging
import uuid
from audio_model.audio_player import AudioPlayer
from controller.state_machine import StateMachine

audio_player = AudioPlayer()
state_machine = StateMachine()

class TTSEngine:
    def __init__(self, voice="zh-CN-XiaoxiaoNeural"):
        self.voice = voice

        # 确保音频输出目录存在
        os.makedirs("data/audio", exist_ok=True)

        logging.info("TTS 引擎初始化完成，使用语音模型：%s", self.voice)

    def speak(self, text: str):
        """
        将文本转换为语音并播放
        """
        filename = f"data/audio/tts_{uuid.uuid4().hex}.mp3"

        logging.info("开始语音合成：%s", text)

        try:
            asyncio.run(self._speak_async(text, filename))
            logging.info("语音合成完成，音频文件已生成：%s", filename)
        except Exception:
            logging.error("语音合成失败", exc_info=True)
            return
        return filename

    def speak_message(self, text: str):
        """播报微信消息（播完 → FSM 进入 WAIT_COMMAND）"""
        logging.info("播报微信消息")
        filename = self.speak(text)

        audio_player.play(
            filename,
            on_finished = state_machine.on_play_finished
        )

    def speak_prompt(self, text: str):
        """播报提示语（不影响 FSM）"""
        logging.info("播报提示语：%s", text)
        filename = self.speak(text)

        audio_player.play(filename)


    # 异步合成
    async def _speak_async(self, text: str, filename:str):
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(filename)
