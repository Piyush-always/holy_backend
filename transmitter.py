import network
import time
import json
import socket
import ssl
import os
from machine import Pin

# ============ CONFIGURATION ============
WIFI_SSID     = "Airtel_Shiv Shakti 2"
WIFI_PASSWORD = "ShivShakti2"
WS_HOST       = "holy-backend-64n1.onrender.com"
WS_PORT       = 443
DEVICE_ID     = "controller1"
TARGET_ID     = "pcb1"

# ============ DIRECTION CODES ============
D_BASE_LEFT  = 0
D_BASE_RIGHT = 1
D_LP_UP      = 2
D_LP_DOWN    = 3
D_RP_UP      = 4
D_RP_DOWN    = 5

DIR_NAMES = ["BASE_L", "BASE_R", "LP_UP", "LP_DN", "RP_UP", "RP_DN"]

# ============ JOYSTICK PINS ============
# Joystick 1 → Left Pump (up/down) + Base (left/right)
JS1_UP    = Pin(2, Pin.IN, Pin.PULL_UP)
JS1_DOWN  = Pin(3, Pin.IN, Pin.PULL_UP)
JS1_LEFT  = Pin(4, Pin.IN, Pin.PULL_UP)
JS1_RIGHT = Pin(5, Pin.IN, Pin.PULL_UP)

# Joystick 2 → Right Pump (up/down) + Base (left/right)
JS2_UP    = Pin(6, Pin.IN, Pin.PULL_UP)
JS2_DOWN  = Pin(7, Pin.IN, Pin.PULL_UP)
JS2_LEFT  = Pin(8, Pin.IN, Pin.PULL_UP)
JS2_RIGHT = Pin(9, Pin.IN, Pin.PULL_UP)

# ============ STATE TRACKING ============
last_state = {
    D_BASE_LEFT:  False,
    D_BASE_RIGHT: False,
    D_LP_UP:      False,
    D_LP_DOWN:    False,
    D_RP_UP:      False,
    D_RP_DOWN:    False,
}

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
            "clientType": "controller",
            "deviceId":   DEVICE_ID
        }))
        print(f"✓ Registered as [{DEVICE_ID}]\n")
        return sock

    except Exception as e:
        print(f"✗ WS error: {e}")
        import sys
        sys.print_exception(e)
        return None

def send_cmd(sock, d, active):
    msg = json.dumps({
        "type": "command",
        "d":    d,
        "s":    1 if active else 0,
        "t":    TARGET_ID
    })
    _ws_send(sock, msg)
    print(f"  {'▶' if active else '■'} {DIR_NAMES[d]}")

# ============ READ JOYSTICKS ============
def read_actions():
    js1_up    = not JS1_UP.value()
    js1_down  = not JS1_DOWN.value()
    js1_left  = not JS1_LEFT.value()
    js1_right = not JS1_RIGHT.value()

    js2_up    = not JS2_UP.value()
    js2_down  = not JS2_DOWN.value()
    js2_left  = not JS2_LEFT.value()
    js2_right = not JS2_RIGHT.value()

    # Conflict resolution for base — if both push opposite, cancel out
    raw_left  = js1_left  or js2_left
    raw_right = js1_right or js2_right

    if raw_left and raw_right:
        # JS1 takes priority; if JS1 neutral, JS2 decides
        base_left  = js1_left  and not js1_right
        base_right = js1_right and not js1_left
        if not base_left and not base_right:
            base_left  = js2_left  and not js2_right
            base_right = js2_right and not js2_left
    else:
        base_left  = raw_left
        base_right = raw_right

    return {
        D_BASE_LEFT:  base_left,
        D_BASE_RIGHT: base_right,
        D_LP_UP:      js1_up,
        D_LP_DOWN:    js1_down,
        D_RP_UP:      js2_up,
        D_RP_DOWN:    js2_down,
    }

# ============ MAIN ============
print("=" * 40)
print("  Spray Bot - Transmitter")
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

        print("Controller ready! Move joysticks.\n")

        try:
            while True:
                current = read_actions()
                for d, active in current.items():
                    if active != last_state[d]:
                        send_cmd(sock, d, active)
                        last_state[d] = active
                time.sleep(0.02)  # 50Hz polling

        except Exception as e:
            print(f"Connection lost: {e}")
            # Send stop for anything still active
            for d, was in last_state.items():
                if was:
                    try: send_cmd(sock, d, False)
                    except: pass
            last_state.update({k: False for k in last_state})
            try: sock.close()
            except: pass
            time.sleep(5)
