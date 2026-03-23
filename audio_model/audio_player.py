# audio_player.py 音频调度模块
import threading
import queue
import logging
import pygame
import time


class AudioPlayer:
    def __init__(self, tts_engine):
        logging.info("AudioPlayer 初始化开始")
        pygame.mixer.init()

        self.tts_engine = tts_engine
        self.queue = queue.PriorityQueue()

        self.is_playing = False
        self.is_paused = False
        self.interrupt_flag = False

        self.current_item = None  # 前播放项（用于回滚）

        self.thread = threading.Thread(target=self._play_loop, daemon=True)
        self.thread.start()

        logging.info("AudioPlayer 初始化完成")

    def play(self, filename, text, before_play=None, on_finished=None, priority=False):
        priority_value = 0 if priority else 2

        self.queue.put((
            priority_value,
            time.time(),
            filename,
            text,
            before_play,
            on_finished
        ))

        logging.info("音频入队：%s", filename)

    def request_interrupt(self):
        logging.info("请求打断播放")
        self.interrupt_flag = True

    def stop(self):
        pygame.mixer.music.stop()

    def stop_all(self):
        self.stop()
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except:
                break

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def _play_loop(self):
        logging.info("播放线程已启动")

        while True:
            try:
                self._play_once()
            except Exception as e:
                logging.error("播放线程异常: %s", e)
                time.sleep(1)

    def _play_once(self):
        item = self.queue.get()
        priority, _, filename, text, before_play, on_finished = item

        # 保存当前播放项
        self.current_item = item

        self.is_playing = True
        self.is_paused = False

        if before_play:
            before_play()

        logging.info("开始播放：%s", filename)

        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()

        interrupted = False

        while pygame.mixer.music.get_busy():
            if self.interrupt_flag:
                logging.info("检测到打断请求")

                pygame.mixer.music.stop()
                self.interrupt_flag = False
                interrupted = True
                break

            if self.is_paused:
                pygame.mixer.music.pause()
                while self.is_paused:
                    time.sleep(0.1)
                pygame.mixer.music.unpause()

            time.sleep(0.1)

        # 如果被打断 → 回滚
        if interrupted:
            logging.info("回滚当前任务：%s", text)

            self.queue.put((
                1,  # 最高优先级
                time.time(),
                filename,
                text,
                before_play,
                on_finished
            ))
        else:
            logging.info("播放完成：%s", filename)

            if on_finished:
                on_finished()

            self.current_item = None

        self.is_playing = False
        self.queue.task_done()