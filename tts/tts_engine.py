# 语音合成模块（Edge TTS）
import threading
import queue
import asyncio
import edge_tts
import os
import logging
import uuid

from audio_model.audio_player import AudioPlayer
from controller.state_machine import StateMachine


class TTSEngine:
    def __init__(self, state_machine, voice="zh-CN-XiaoxiaoNeural"):
        self.voice = voice
        self.audio_player = AudioPlayer(self)
        self.is_playing = False
        self.is_paused = False
        self.current_file = None
        self.state_machine = state_machine

        self.queue = queue.Queue()

        os.makedirs("data/audio", exist_ok=True)

        # 启动 TTS 后台线程
        self.worker_thread = threading.Thread(
            target=self._tts_loop,
            daemon=True
        )
        self.worker_thread.start()

        logging.info("TTS 引擎初始化完成")

    def speak(self, text: str):
        """
        HTTP 线程只负责入队
        """
        logging.info("文本入队：%s", text)
        self.queue.put(text)

    def _tts_loop(self):
        """
        单线程顺序执行 TTS
        """
        while True:
            text = self.queue.get()
            filename = f"data/audio/tts_{uuid.uuid4().hex}.mp3"

            try:
                logging.info("开始语音合成：%s", text)
                asyncio.run(self._speak_async(text, filename))
                logging.info("语音合成完成：%s", filename)

                self.audio_player.play(
                    filename,
                    on_finished=self.state_machine.on_play_finished
                )

            except Exception:
                logging.error("TTS 失败", exc_info=True)

            self.queue.task_done()

    async def _speak_async(self, text: str, filename: str):
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
        )
        await communicate.save(filename)

    def stop(self):
        logging.info("清空 TTS 队列")
        while not self.queue.empty():
            self.queue.get()
            self.queue.task_done()

        self.audio_player.stop()
        self.is_playing = False
