# 状态机模块
import logging
from enum import Enum, auto

# 定义系统枚举状态
class SystemState(Enum):
    IDLE = auto()               # 空闲状态 
    MESSAGE_PLAYING = auto()    # 消息播放中
    WAIT_COMMAND = auto()       # 等待语音指令
    REPLY_MODE = auto()         # 回复模式


class StateMachine:
    def __init__(self):
        self.state = SystemState.IDLE
        logging.info("状态机初始化，当前状态：IDLE")

    # 状态切换方法
    def set_state(self, new_state: SystemState):
        logging.info("状态切换：%s → %s", self.state.name, new_state.name)
        self.state = new_state

    # 收到新消息
    def on_message_received(self):
        if self.state == SystemState.IDLE:
            self.set_state(SystemState.MESSAGE_PLAYING)

    # 播放完成
    def on_play_finished(self):
        if self.state == SystemState.MESSAGE_PLAYING:
            self.set_state(SystemState.WAIT_COMMAND)

    # 收到语音指令
    def on_command(self, command: str):
        if self.state != SystemState.WAIT_COMMAND:
            logging.warning("当前状态不接受指令")
            return

        if command == "REPLY":
            self.set_state(SystemState.REPLY_MODE)
        elif command == "REPEAT":
            self.set_state(SystemState.MESSAGE_PLAYING)
        elif command in ("IGNORE", "EXIT"):
            self.set_state(SystemState.IDLE)
        else:
            logging.warning("未知指令：%s", command)
