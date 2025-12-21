from tts.tts_engine import TTSEngine
from asr.command_parser import CommandASR
import time

tts = TTSEngine()
asr = CommandASR()

tts.speak("测试语音播报，请说出指令")

time.sleep(1)

cmd = asr.listen_command()
print("识别到指令:", cmd)
