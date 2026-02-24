import network
import time
import json
import socket
import ssl
import os
from machine import Pin
import _thread

# ============ CONFIGURATION ============
WIFI_SSID     = "Airtel_Shiv Shakti 2"
WIFI_PASSWORD = "ShivShakti2"
WS_HOST       = "holy-backend-64n1.onrender.com"
WS_PORT       = 443
DEVICE_ID     = "pcb1"

# ============ DIRECTION CODES ============
# Must match transmitter
D_BASE_LEFT   = 0
D_BASE_RIGHT  = 1
D_LP_UP       = 2
D_LP_DOWN     = 3
D_RP_UP       = 4
D_RP_DOWN     = 5

DIR_NAMES = {
    D_BASE_LEFT:  "BASE_L",
    D_BASE_RIGHT: "BASE_R",
    D_LP_UP:      "LP_UP",
    D_LP_DOWN:    "LP_DN",
    D_RP_UP:      "RP_UP",
    D_RP_DOWN:    "RP_DN",
}

# ============ STEPPER SETUP ============
HALF_STEP = [
    [1,0,0,0],[1,1,0,0],[0,1,0,0],[0,1,1,0],
    [0,0,1,0],[0,0,1,1],[0,0,0,1],[1,0,0,1],
]
STEP_DELAY = 0.002

class Stepper:
    def __init__(self, p1, p2, p3, p4):
        self.pins = [Pin(p1,Pin.OUT), Pin(p2,Pin.OUT),
                     Pin(p3,Pin.OUT), Pin(p4,Pin.OUT)]
        self.idx = 0

    def step(self, direction):
        self.idx = (self.idx + direction) % 8
        for i, p in enumerate(self.pins):
            p.value(HALF_STEP[self.idx][i])
        time.sleep(STEP_DELAY)

    def stop(self):
        for p in self.pins: p.value(0)

# ============ MOTORS ============
# Change pins to match your wiring
left_pump  = Stepper(2,  3,  4,  5)
right_pump = Stepper(6,  7,  8,  9)
base       = Stepper(10, 11, 12, 13)

# direction code → (motor object, step direction)
MOTOR_MAP = {
    D_BASE_LEFT:  (base,        1),
    D_BASE_RIGHT: (base,       -1),
    D_LP_UP:      (left_pump,   1),
    D_LP_DOWN:    (left_pump,  -1),
    D_RP_UP:      (right_pump,  1),
    D_RP_DOWN:    (right_pump, -1),
}

# Active direction per motor (None = stopped)
# Only one direction per motor can be active
motor_active = {
    "base":       None,
    "left_pump":  None,
    "right_pump": None,
}

MOTOR_NAMES = {
    D_BASE_LEFT:  "base",
    D_BASE_RIGHT: "base",
    D_LP_UP:      "left_pump",
    D_LP_DOWN:    "left_pump",
    D_RP_UP:      "right_pump",
    D_RP_DOWN:    "right_pump",
}

# ============ MOTOR THREAD ============
def motor_runner():
    while True:
        moved = False
        for motor_name, direction_code in motor_active.items():
            if direction_code is not None:
                motor_obj, step_dir = MOTOR_MAP[direction_code]
                motor_obj.step(step_dir)
                moved = True
        if not moved:
            time.sleep(0.01)

def stop_all():
    for k in motor_active:
        motor_active[k] = None
    left_pump.stop()
    right_pump.stop()
    base.stop()

# ============ COMMAND HANDLER ============
def handle(msg):
    d = msg.get('d')   # direction code
    s = msg.get('s')   # 1=start, 0=stop

    if d is None or s is None:
        return

    motor_name = MOTOR_NAMES.get(d)
    if not motor_name:
        print(f"  ? Unknown direction: {d}")
        return

    name = DIR_NAMES.get(d, str(d))

    if s == 1:
        motor_active[motor_name] = d
        print(f"  ▶ {name}")
    else:
        # Only stop if this direction is currently the active one
        if motor_active[motor_name] == d:
            motor_active[motor_name] = None
            MOTOR_MAP[d][0].stop()
        print(f"  ■ {name}")

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
        print(f"✓ IP: {wlan.ifconfig()[0]}\n")
        return True
    return False

# ============ WEBSOCKET ============
def _ws_send(sock, text):
    b = text.encode('utf-8')
    mask = os.urandom(4)
    frame = bytearray([0x81, 0x80 | len(b)])
    frame.extend(mask)
    for i, byte in enumerate(b):
        frame.append(byte ^ mask[i % 4])
    sock.send(bytes(frame))

def connect_websocket():
    try:
        addr = socket.getaddrinfo(WS_HOST, WS_PORT)[0][-1]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(addr)
        sock = ssl.wrap_socket(sock, server_hostname=WS_HOST)

        sock.send((
            "GET / HTTP/1.1\r\n"
            f"Host: {WS_HOST}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode())

        if "101" not in sock.recv(1024).decode():
            return None

        _ws_send(sock, json.dumps({
            "type": "register",
            "clientType": "pcb",
            "deviceId": DEVICE_ID
        }))
        print(f"✓ WS connected [{DEVICE_ID}]\n")
        return sock
    except Exception as e:
        print(f"✗ {e}")
        return None

def recv_msg(sock):
    try:
        h = sock.recv(2)
        if len(h) < 2: return None
        l = h[1] & 0x7F
        if l == 126: l = int.from_bytes(sock.recv(2), 'big')
        elif l == 127: l = int.from_bytes(sock.recv(8), 'big')
        p = sock.recv(l)
        return json.loads(p.decode()) if p else None
    except:
        return None

# ============ MAIN ============
print("== Spray Bot Receiver ==\n")

if not connect_wifi():
    print("WiFi failed.")
else:
    _thread.start_new_thread(motor_runner, ())
    print("✓ Motor thread started")

    while True:
        sock = connect_websocket()
        if not sock:
            print("Retry in 3s...")
            time.sleep(3)
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
            time.sleep(3)
