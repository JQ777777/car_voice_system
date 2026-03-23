# state_machine.py 状态机模块
import logging
from enum import Enum, auto

# 定义系统枚举状态
class SystemState(Enum):
    OFF = auto()                # 系统关闭（最高层）
    IDLE = auto()               # 空闲状态 
    MESSAGE_PLAYING = auto()    # 消息播放中
    WAIT_COMMAND = auto()       # 等待语音指令
    REPLY_MODE_CONTACT = auto() # 等联系人
    REPLY_MODE_CONTENT = auto() # 等内容


class StateMachine:
    def __init__(self):
        self.state = SystemState.OFF   # 默认关闭
        logging.info("状态机初始化, 当前状态: OFF")

    # 状态切换方法
    def set_state(self, new_state: SystemState):
        logging.info("状态切换：%s → %s", self.state.name, new_state.name)
        self.state = new_state

    def turn_on(self):
        if self.state == SystemState.OFF:
            logging.info("系统开启")
            self.set_state(SystemState.IDLE)

    def turn_off(self):
        logging.info("系统关闭")
        self.set_state(SystemState.OFF)

    def on_message_received(self):
        logging.info("on_message_received | 当前状态：%s", self.state)

        # 关闭状态直接忽略
        if self.state == SystemState.OFF:
            logging.info("系统关闭，忽略消息")
            return

        if self.state in [SystemState.IDLE, SystemState.WAIT_COMMAND]:
            self.set_state(SystemState.MESSAGE_PLAYING)

    def on_play_finished(self):
        if self.state == SystemState.MESSAGE_PLAYING:
            self.set_state(SystemState.WAIT_COMMAND)

    def on_command(self, command: str):
        logging.info("on_command: %s | 当前状态：%s", command, self.state)

        # OFF 状态只允许 OPEN
        if self.state == SystemState.OFF:
            if command == "OPEN":
                self.turn_on()
            else:
                logging.info("系统未开启，仅接受 OPEN 指令")
            return

        # 任何状态都允许 EXIT
        if command == "EXIT":
            self.turn_off()
            return

        # 只有 WAIT_COMMAND 才处理普通指令
        if self.state != SystemState.WAIT_COMMAND:
            logging.warning("当前状态不接受指令")
            return

        if command == "REPLY":
            self.set_state(SystemState.REPLY_MODE_CONTACT)

        elif command == "REPEAT":
            self.set_state(SystemState.MESSAGE_PLAYING)

        else:
            logging.warning("未知指令：%s", command)