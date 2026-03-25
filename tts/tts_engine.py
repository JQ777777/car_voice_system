# tts_engine.py 语音合成模块
import threading
import queue
import asyncio
import edge_tts
import os
import logging
import uuid
import time
import subprocess
import hashlib

from audio_model.audio_player import AudioPlayer
from tts.piper_engine import PiperEngine


class TTSEngine:
    def __init__(self, state_machine, voice="zh-CN-XiaoxiaoNeural", mode="edge"):
        self.voice = voice
        self.mode = mode
        if self.mode == "piper":
            self.piper = PiperEngine()
        self.audio_player = AudioPlayer(self)
        self.state_machine = state_machine

        self.queue = queue.PriorityQueue()

        self.current_playing_text = None
        self.last_played_text = None

        #self.interrupt_flag = False

        # 系统总开关
        self.enabled = True

        # 缓存
        self.text_audio_map = {}

        os.makedirs("data/audio", exist_ok=True)

        self.worker_thread = threading.Thread(
            target=self._tts_loop,
            daemon=True
        )
        self.worker_thread.start()

        logging.info("TTS 引擎初始化完成")

        self._preload_common_texts()

    def speak(self, text: str, priority=False):
        # 系统关闭直接丢弃
        if not self.enabled:
            logging.info("系统关闭，丢弃文本：%s", text)
            return

        logging.info("文本入队：%s", text)

        # 高优先级 + 命中缓存 → 直接播放（不走TTS）
        if text in self.text_audio_map:
            logging.info("命中缓存，直接播放：%s", text)

            filename = self.text_audio_map[text]

            self.audio_player.play(
                filename,
                text=text,
                priority=priority
            )
            return

        # 优先级体系
        # 0 = 用户指令（重复）
        # 1 = 回滚任务
        # 2 = 普通消息
        priority_value = 0 if priority else 2

        self.queue.put((
            priority_value,
            time.time(),
            text
        ))

    # def request_interrupt(self):
    #     logging.info("请求打断 TTS")
    #     self.interrupt_flag = True

    def _tts_loop(self):
        while True:
            priority, _, text = self.queue.get()

            # 系统关闭 → 丢弃任务
            if not self.enabled:
                logging.info("系统关闭，丢弃TTS任务：%s", text)
                self.queue.task_done()
                continue

            if self.mode == "edge":
                filename = f"data/audio/tts_{uuid.uuid4().hex}.mp3"
            else:
                filename = f"data/audio/tts_{uuid.uuid4().hex}.wav"

            try:
                logging.info("开始语音合成：%s", text)

                if self.mode == "edge":
                    asyncio.run(self._speak_async(text, filename))
                    output_file = filename
                else:
                    output_file = self.piper.synthesize(text, filename)

                # 合成过程中被打断 → 回滚（不丢）
                # if self.interrupt_flag:
                #     logging.info("合成完成但被打断，重新入队：%s", text)

                #     self.queue.put((
                #         1,  # 回滚优先级
                #         time.time(),
                #         text
                #     ))

                #     self.interrupt_flag = False
                #     self.queue.task_done()
                #     continue

                # 系统关闭（双保险）
                if not self.enabled:
                    logging.info("系统关闭，丢弃已合成音频：%s", text)
                    self.queue.task_done()
                    continue

                logging.info("语音合成完成：%s", filename)

                # 写缓存
                self.text_audio_map[text] = output_file

                def before_play(text=text):
                    self.current_playing_text = text
                    logging.info("当前播放内容：%s", text)

                def final_callback(text=text):
                    try:
                        self.last_played_text = text
                        logging.info("正确记录上一条：%s", text)

                        self.current_playing_text = None

                        # 只有开启状态才触发状态机
                        if self.enabled:
                            self.state_machine.on_play_finished()

                    except Exception as e:
                        logging.error("播放完成回调异常: %s", e)

                self.audio_player.play(
                    output_file,
                    text=text,
                    before_play=before_play,
                    on_finished=final_callback,
                    priority=(priority == 0)
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

    def _speak_piper(self, text: str, filename: str):
        try:
            output_file = self.piper.synthesize(text)

            # 等待文件生成（简单同步）
            while not os.path.exists(output_file):
                time.sleep(0.01)

            return output_file

        except Exception as e:
            logging.error("Piper TTS失败: %s", e)
            raise

    def _preload_common_texts(self):
        if self.mode != "piper":
            return  # 只对离线模式做预加载

        logging.info("开始预加载常用语音...")

        common_texts = [
            "系统已开启",
            "请说联系人",
            "请说回复内容"
        ]

        for text in common_texts:
            try:
                # 生成安全文件名
                safe_name = hashlib.md5(text.encode("utf-8")).hexdigest()
                filename = f"data/audio/pre_{safe_name}.wav"

                # 如果文件已存在 → 直接用
                if os.path.exists(filename):
                    logging.info("命中本地缓存文件：%s", text)
                    self.text_audio_map[text] = filename

                else:
                    output_file = self.piper.synthesize(text, filename)

                    if os.path.exists(output_file):
                        self.text_audio_map[text] = output_file
                        logging.info("预加载成功：%s", text)
                    else:
                        logging.warning("文件未生成，不加入缓存：%s", text)

            except Exception as e:
                logging.error("预加载失败：%s | %s", text, e)

    def stop(self):
        self.audio_player.stop()

    def stop_all(self):
        self.audio_player.stop_all()

    def clear_all(self):
        """
        彻底清空系统(EXIT用)
        """
        logging.info("清空TTS系统所有任务")

        # 清空TTS队列
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except:
                break

        # 停止播放 + 清空播放队列
        self.audio_player.stop_all()

    def enable(self):
        logging.info("TTS系统开启")
        self.enabled = True

    def disable(self):
        logging.info("TTS系统关闭")
        self.enabled = False
        self.clear_all()

    def pause(self):
        self.audio_player.pause()

    def resume(self):
        self.audio_player.resume()

    @property
    def is_playing(self):
        return self.audio_player.is_playing