# 音频调度模块
import queue
import threading
import os
import logging
from playsound import playsound

class AudioPlayer:
    def __init__(self):
        self.queue = queue.Queue()
        self.thread = threading.Thread(
            target=self._play_loop,
            daemon=True
        )
        self.thread.start()

    def play(self, filename: str, on_finished=None):
        logging.info("音频入队：%s", filename)
        self.queue.put((filename, on_finished))

    def _play_loop(self):
        while True:
            filename, on_finished = self.queue.get()
            try:
                logging.info("开始播放：%s", filename)
                playsound(filename)  # 阻塞播放
                logging.info("播放完成：%s", filename)
            except Exception:
                logging.error("播放失败", exc_info=True)
            finally:
                if on_finished:
                    on_finished()
                self.queue.task_done()
