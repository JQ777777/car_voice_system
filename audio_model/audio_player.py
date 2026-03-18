# 音频调度模块
import threading
import queue
import logging
import pygame
import time


class AudioPlayer:
    def __init__(self, tts_engine):
        pygame.mixer.init()
        self.tts_engine = tts_engine
        self.queue = queue.Queue()

        self.is_playing = False
        self.is_paused = False

        self.thread = threading.Thread(target=self._play_loop, daemon=True)
        self.thread.start()
        logging.info("AudioPlayer 初始化完成")

    def play(self, filename: str, on_finished=None):
        logging.info("音频入队：%s", filename)
        self.queue.put((filename, on_finished))

    def stop(self):
        logging.info("停止当前播放")
        pygame.mixer.music.stop()
        self.is_playing = False

        # 清空队列（关键！）
        while not self.queue.empty():
            self.queue.get()
            self.queue.task_done()
    
    def pause(self):
        logging.info("暂停播放")
        self.is_paused = True

    def resume(self):
        logging.info("恢复播放")
        self.is_paused = False

    def _play_loop(self):
        while True:
            filename, on_finished = self.queue.get()

            try:
                # 开始播放 → 标记为 True
                self.is_playing = True
                self.is_paused = False

                logging.info("开始播放：%s", filename)

                pygame.mixer.music.load(filename)
                pygame.mixer.music.play()

                # 等待播放结束
                while pygame.mixer.music.get_busy():
                    if self.is_paused:
                        pygame.mixer.music.pause()
                        while self.is_paused:
                            time.sleep(0.1)
                        pygame.mixer.music.unpause()

                    time.sleep(0.1)

                logging.info("播放完成：%s", filename)

            except Exception:
                logging.error("播放失败：%s", filename, exc_info=True)

            finally:
                # 播放结束 → 标记为 False
                self.is_playing = False

                if on_finished:
                    on_finished()

                self.queue.task_done()
