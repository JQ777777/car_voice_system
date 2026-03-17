# 音频调度模块
import threading
import queue
import logging
import pygame
import time


class AudioPlayer:
    def __init__(self):
        pygame.mixer.init()
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._play_loop, daemon=True)
        self.thread.start()
        logging.info("AudioPlayer 初始化完成")

    def play(self, filename: str, on_finished=None):
        logging.info("音频入队：%s", filename)
        self.queue.put((filename, on_finished))

    def _play_loop(self):
        while True:
            filename, on_finished = self.queue.get()

            try:
                logging.info("开始播放：%s", filename)

                pygame.mixer.music.load(filename)
                pygame.mixer.music.play()

                # 等待播放结束
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)

                logging.info("播放完成：%s", filename)

            except Exception:
                logging.error("播放失败：%s", filename, exc_info=True)

            finally:
                if on_finished:
                    on_finished()

                self.queue.task_done()
