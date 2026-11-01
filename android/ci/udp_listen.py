"""Слушает OSC (7000) и Live Link (54321) на машине CI и считает пакеты от эмулятора."""
import json
import socket
import select
import sys
import time

dur = float(sys.argv[1]) if len(sys.argv) > 1 else 40
socks = {}
for port in (7000, 54321):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    socks[s] = port
counts = {7000: 0, 54321: 0}
osc_addrs, last_ll = set(), None
t0 = time.time()
while time.time() - t0 < dur:
    r, _, _ = select.select(list(socks), [], [], 0.5)
    for s in r:
        data, _ = s.recvfrom(65535)
        port = socks[s]
        counts[port] += 1
        if port == 7000:
            osc_addrs.add(data.split(b"\0", 1)[0].decode(errors="replace"))
        else:
            last_ll = data
print("OSC messages:", counts[7000], "addresses:", sorted(osc_addrs)[:8])
print("Live Link packets:", counts[54321])
if last_ll:
    pkt = json.loads(last_ll)
    print("Live Link last packet: v=%s prefix=%s persons=%d" % (pkt["v"], pkt["prefix"], len(pkt["persons"])))
ok = counts[7000] > 0 and counts[54321] > 0
print("RESULT:", "OK" if ok else "NO DATA")
sys.exit(0 if ok else 1)
