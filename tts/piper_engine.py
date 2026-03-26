# piper_engine.py
import subprocess
import threading
import queue
import os
import uuid
import logging
import json

class PiperEngine:
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.piper_path = os.path.join(base_dir, "piper", "piper.exe")
        self.model_path = os.path.join(base_dir, "models", "piper", "zh_CN-huayan-medium.onnx")
        self.config_path = self.model_path + ".json"

        self._start()

    def _start(self):
        self.process = subprocess.Popen(
            [
                self.piper_path,
                "--model", self.model_path,
                "--config", self.config_path,
                "--json-input",
                "--length_scale", "0.9",
                "--noise_scale", "0.6",
                "--noise_w", "0.8",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,   # ⭐关键
            bufsize=1
        )

        print("✅ Piper 常驻启动成功")

    def synthesize(self, text, output_file):
        data = {
            "text": text,
            "output_file": output_file
        }

        # 写入
        self.process.stdin.write(json.dumps(data) + "\n")
        self.process.stdin.flush()

        # ⭐必须读一行，否则会卡死
        result = self.process.stdout.readline()

        return output_file

    def _worker_loop(self):
        while True:
            text, output_file = self.queue.get()

            try:
                logging.info("🗣️ Piper合成: %s", text)

                command = [
                    self.piper_path,
                    "--model", self.model_path,
                    "--output_file", output_file,
                    "--text", text
                ]

                subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                logging.info("✅ Piper生成完成: %s", output_file)

            except Exception as e:
                logging.error("Piper处理失败: %s", e)

            self.queue.task_done()

    def _read_audio_stream(self):
        """
        读取 stdout 音频流（核心）
        """
        chunks = []
        while True:
            chunk = self.process.stdout.read(4096)
            if not chunk:
                break
            chunks.append(chunk)

            # ⚠️ 简单截断策略（避免无限读）
            if len(chunk) < 4096:
                break

        return b"".join(chunks)