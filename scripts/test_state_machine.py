from controller.state_machine import StateMachine, SystemState

sm = StateMachine()

sm.on_message_received()
assert sm.state == SystemState.MESSAGE_PLAYING

sm.on_play_finished()
assert sm.state == SystemState.WAIT_COMMAND

sm.on_command("IGNORE")
assert sm.state == SystemState.IDLE

print("状态机测试通过")
