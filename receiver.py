import network
import time
import json
import socket
import ssl
import os
from machine import Pin

# ============ CONFIGURATION ============
WIFI_SSID     = "Hotspot"
WIFI_PASSWORD = "12345678"
WS_HOST       = "holy-backend-64n1.onrender.com"
WS_PORT       = 443
DEVICE_ID     = "pcb1"

# ============ DIRECTION CODES ============
D_BASE_LEFT  = 0
D_BASE_RIGHT = 1
D_LP_UP      = 2
D_LP_DOWN    = 3
D_RP_UP      = 4
D_RP_DOWN    = 5

DIR_NAMES = {
    0: "BASE_L",
    1: "BASE_R",
    2: "LP_UP",
    3: "LP_DN",
    4: "RP_UP",
    5: "RP_DN",
}

# ============ RELAY PINS ============
# One GPIO per direction → connects to relay module input
# GP2=Base Left, GP3=Base Right, GP4=LP Up, GP5=LP Down, GP6=RP Up, GP7=RP Down
relay_pins = {
    D_BASE_LEFT:  Pin(2, Pin.OUT),
    D_BASE_RIGHT: Pin(3, Pin.OUT),
    D_LP_UP:      Pin(4, Pin.OUT),
    D_LP_DOWN:    Pin(5, Pin.OUT),
    D_RP_UP:      Pin(6, Pin.OUT),
    D_RP_DOWN:    Pin(7, Pin.OUT),
}

# Conflict pairs — only one per pair can be HIGH at a time (last wins)
CONFLICT_PAIRS = [
    (D_BASE_LEFT,  D_BASE_RIGHT),
    (D_LP_UP,      D_LP_DOWN),
    (D_RP_UP,      D_RP_DOWN),
]

# All relays OFF at boot
for p in relay_pins.values():
    p.value(0)

# ============ COMMAND HANDLER ============
def handle(msg):
    d = msg.get('d')
    s = msg.get('s')

    if d is None or s is None:
        return
    if d not in relay_pins:
        print(f"  ? Unknown d: {d}")
        return

    name = DIR_NAMES.get(d, str(d))

    if s == 1:
        # Turn off conflicting pin first
        for pair in CONFLICT_PAIRS:
            if d in pair:
                other = pair[1] if pair[0] == d else pair[0]
                if relay_pins[other].value() == 1:
                    relay_pins[other].value(0)
                    print(f"  ✗ Cleared conflict: {DIR_NAMES[other]}")
                break
        relay_pins[d].value(1)
        print(f"  ▶ {name} ON")

    else:
        relay_pins[d].value(0)
        print(f"  ■ {name} OFF")

def stop_all():
    for p in relay_pins.values():
        p.value(0)
    print("  All relays OFF")

# ============ WIFI ============
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    print("Connecting to WiFi...")
    timeout = 10
    while not wlan.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1
    if wlan.isconnected():
        ip, subnet, gateway, _ = wlan.ifconfig()
        wlan.ifconfig((ip, subnet, gateway, '8.8.8.8'))
        print(f"✓ WiFi connected! IP: {ip}\n")
        return True
    print("✗ WiFi failed")
    return False

# ============ WEBSOCKET ============
def _ws_send(sock, text):
    msg_bytes = text.encode('utf-8')
    mask = os.urandom(4)
    frame = bytearray([0x81, 0x80 | len(msg_bytes)])
    frame.extend(mask)
    for i, byte in enumerate(msg_bytes):
        frame.append(byte ^ mask[i % 4])
    sock.send(bytes(frame))

def connect_websocket():
    import gc
    gc.collect()
    try:
        print("Connecting to WebSocket...")
        addr = socket.getaddrinfo(WS_HOST, WS_PORT)[0][-1]
        print(f"Resolved: {addr}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(addr)
        sock = ssl.wrap_socket(sock, server_hostname=WS_HOST)
        print("✓ SSL connected")

        # WebSocket handshake
        sock.send((
            "GET / HTTP/1.1\r\n"
            f"Host: {WS_HOST}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode())

        response = sock.recv(1024).decode()
        if "101" not in response:
            print(f"✗ Handshake failed: {response[:80]}")
            sock.close()
            return None
        print("✓ WebSocket handshake OK")

        # Register
        _ws_send(sock, json.dumps({
            "type":       "register",
            "clientType": "pcb",
            "deviceId":   DEVICE_ID
        }))
        print(f"✓ Registered as [{DEVICE_ID}]\n")
        return sock

    except Exception as e:
        print(f"✗ WS error: {e}")
        import sys
        sys.print_exception(e)
        return None

def recv_msg(sock):
    try:
        h = sock.recv(2)
        if len(h) < 2:
            return None
        l = h[1] & 0x7F
        if l == 126: l = int.from_bytes(sock.recv(2), 'big')
        elif l == 127: l = int.from_bytes(sock.recv(8), 'big')
        p = sock.recv(l)
        return json.loads(p.decode()) if p else None
    except:
        return None

# ============ MAIN ============
print("=" * 40)
print("  Spray Bot - Receiver (Relay Mode)")
print("=" * 40 + "\n")

if not connect_wifi():
    print("Exiting.")
else:
    while True:
        sock = connect_websocket()
        if not sock:
            print("Retry in 5s...")
            time.sleep(5)
            continue

        print("Listening for commands...\n")

        try:
            while True:
                msg = recv_msg(sock)
                if msg is None:
                    print("Connection lost.")
                    break
                if msg.get('type') == 'command' or 'd' in msg:
                    t = time.localtime()
                    print(f"[{t[3]:02d}:{t[4]:02d}:{t[5]:02d}] d={msg.get('d')} s={msg.get('s')}")
                    handle(msg)

        except Exception as e:
            print(f"Error: {e}")
        finally:
            stop_all()
            try: sock.close()
            except: pass
            time.sleep(5)
