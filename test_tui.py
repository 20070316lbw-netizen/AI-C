from aic.tui import TUIRenderer
import time

tui = TUIRenderer()
tui.start()
try:
    user_input = input("> ")
    tui.render_message("user", user_input)
    time.sleep(1)
finally:
    tui.stop()
