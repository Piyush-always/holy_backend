import network
import time
import json
import socket
import ssl

# ============ CONFIGURATION ============
WIFI_SSID = "Airtel_Shiv Shakti 2"
WIFI_PASSWORD = "ShivShakti2"
WEBSOCKET_URL = "holybackend-production.up.railway.app"
DEVICE_ID = "pcb1"

# ============ CONNECT WIFI ============
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    
    print("Connecting to WiFi...")
    while not wlan.isconnected():
        time.sleep(1)
    
    print(f"Connected! IP: {wlan.ifconfig()[0]}")

# ============ WEBSOCKET ============
def connect_websocket():
    addr = socket.getaddrinfo(WEBSOCKET_URL, 443)[0][-1]
    sock = socket.socket()
    sock = ssl.wrap_socket(sock)
    sock.connect(addr)
    
    # WebSocket handshake
    handshake = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {WEBSOCKET_URL}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.send(handshake.encode())
    sock.recv(1024)
    
    # Register device
    register_msg = json.dumps({
        "type": "register",
        "clientType": "pcb",
        "deviceId": DEVICE_ID
    })
    sock.send(create_frame(register_msg))
    
    print("WebSocket connected!\n")
    return sock

def create_frame(message):
    msg_bytes = message.encode('utf-8')
    frame = bytearray([0x81])
    
    length = len(msg_bytes)
    if length < 126:
        frame.append(0x80 | length)
    else:
        frame.append(0x80 | 126)
        frame.extend(length.to_bytes(2, 'big'))
    
    mask = bytes([0x12, 0x34, 0x56, 0x78])
    frame.extend(mask)
    
    for i, byte in enumerate(msg_bytes):
        frame.append(byte ^ mask[i % 4])
    
    return bytes(frame)

def receive_message(sock):
    header = sock.recv(2)
    if len(header) < 2:
        return None
    
    payload_len = header[1] & 0x7F
    
    if payload_len == 126:
        payload_len = int.from_bytes(sock.recv(2), 'big')
    elif payload_len == 127:
        payload_len = int.from_bytes(sock.recv(8), 'big')
    
    payload = sock.recv(payload_len)
    return json.loads(payload.decode('utf-8'))

# ============ MAIN ============
connect_wifi()
sock = connect_websocket()

print("Listening for commands...\n")
print("-" * 50)

while True:
    try:
        msg = receive_message(sock)
        
        if msg and msg.get('type') == 'command':
            timestamp = time.localtime()
            time_str = f"{timestamp[3]:02d}:{timestamp[4]:02d}:{timestamp[5]:02d}"
            
            action = msg.get('action', 'UNKNOWN')
            print(f"[{time_str}] Command: {action}")
    
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
        sock = connect_websocket()

