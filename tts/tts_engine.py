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
        入队 + 播放完成回调
        """
        logging.info("文本入队：%s", text)

        # 定义播放完成回调
        def on_finished():
            try:
                import server.http_server as http_server
                http_server.last_played_message = text
                logging.info("记录上一条播放内容：%s", text)
            except Exception as e:
                logging.warning("记录 last_played_message 失败: %s", e)

        # 入队
        self.queue.put((text, on_finished))

    def _tts_loop(self):
        """
        单线程顺序执行 TTS
        """
        while True:
            text, on_finished = self.queue.get()
            filename = f"data/audio/tts_{uuid.uuid4().hex}.mp3"

            try:
                logging.info("开始语音合成：%s", text)
                asyncio.run(self._speak_async(text, filename))
                logging.info("语音合成完成：%s", filename)

                # 合并两个回调
                def final_callback():
                    try:
                        # ① 记录上一条播放
                        if on_finished:
                            on_finished()

                        # ② 状态机回调
                        self.state_machine.on_play_finished()

                    except Exception as e:
                        logging.error("播放完成回调异常: %s", e)

                # 传入 audio_player
                self.audio_player.play(
                    filename,
                    on_finished=final_callback
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
        self.audio_player.stop()

    def pause(self):
        self.audio_player.pause()

    def resume(self):
        self.audio_player.resume()

    @property
    def is_playing(self):
        return self.audio_player.is_playing
