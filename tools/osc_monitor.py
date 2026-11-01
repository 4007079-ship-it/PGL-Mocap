"""Простой монитор OSC: показывает, что реально приходит на порт.

Запуск:  python tools/osc_monitor.py 7000
Полезно, чтобы проверить работу PGL Mocap без Aximmetry (закройте Aximmetry
или укажите в PGL Mocap другой порт — один порт может слушать только одна программа).
"""
import sys
import time

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

port = int(sys.argv[1]) if len(sys.argv) > 1 else 7000
last = {}


def handler(addr, *args):
    now = time.time()
    if now - last.get(addr, 0) > 0.5:          # не чаще 2 раз в секунду на адрес
        last[addr] = now
        vals = " ".join(f"{a:+.3f}" if isinstance(a, float) else str(a) for a in args)
        print(f"{addr:<40} {vals}")


d = Dispatcher()
d.set_default_handler(handler)
print(f"Слушаю OSC на порту {port}... (Ctrl+C — выход)")
BlockingOSCUDPServer(("0.0.0.0", port), d).serve_forever()
