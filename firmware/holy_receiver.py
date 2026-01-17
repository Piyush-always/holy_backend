import network
import time
import json
import socket
import ssl

# ============ CONFIGURATION ============
WIFI_SSID = "Airtel_Shiv Shakti 2"
WIFI_PASSWORD = "ShivShakti2"
WEBSOCKET_HOST = "holy-backend-64n1.onrender.com"  # Remove https://
WEBSOCKET_PORT = 443
DEVICE_ID = "pcb1"

# ============ CONNECT WIFI ============
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
        print(f"✓ Connected! IP: {wlan.ifconfig()[0]}\n")
        return True
    return False

# ============ WEBSOCKET WITH SSL ============
def connect_websocket():
    try:
        print("Connecting to WebSocket server...")
        addr_info = socket.getaddrinfo(WEBSOCKET_HOST, WEBSOCKET_PORT)
        addr = addr_info[0][-1]
        
        print(f"Resolved to: {addr}")
        
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(addr)
        print("✓ Socket connected")
        
        # Wrap with SSL
        sock = ssl.wrap_socket(sock, server_hostname=WEBSOCKET_HOST)
        print("✓ SSL wrapped")
        
        # WebSocket handshake
        handshake = (
            "GET / HTTP/1.1\r\n"
            f"Host: {WEBSOCKET_HOST}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.send(handshake.encode())
        response = sock.recv(1024).decode()
        
        if "101" not in response:
            print(f"Handshake failed. Response: {response[:100]}")
            return None
        
        print("✓ WebSocket handshake successful")
        
        # Register device
        register_msg = json.dumps({
            "type": "register",
            "clientType": "pcb",
            "deviceId": DEVICE_ID
        })
        
        msg_bytes = register_msg.encode('utf-8')
        frame = bytearray([0x81, 0x80 | len(msg_bytes)])
        mask = bytes([0x12, 0x34, 0x56, 0x78])
        frame.extend(mask)
        for i, byte in enumerate(msg_bytes):
            frame.append(byte ^ mask[i % 4])
        sock.send(bytes(frame))
        
        print(f"✓ Registered as: {DEVICE_ID}")
        return sock
        
    except Exception as e:
        print(f"✗ Connection error: {e}")
        import sys
        sys.print_exception(e)
        return None

def receive_message(sock):
    try:
        header = sock.recv(2)
        
        if len(header) < 2:
            return None
        
        payload_len = header[1] & 0x7F
        
        if payload_len == 126:
            payload_len = int.from_bytes(sock.recv(2), 'big')
        elif payload_len == 127:
            payload_len = int.from_bytes(sock.recv(8), 'big')
        
        payload = sock.recv(payload_len)
        
        if payload:
            return json.loads(payload.decode('utf-8'))
        return None
        
    except Exception as e:
        return None

# ============ MAIN ============
print("="*50)
print("  Raspberry Pi Pico W - Render Server")
print("="*50 + "\n")

if not connect_wifi():
    print("WiFi failed. Exiting.")
else:
    sock = connect_websocket()
    
    if sock:
        print("\n" + "-"*50)
        print("Listening for commands...")
        print("-"*50 + "\n")
        
        try:
            while True:
                msg = receive_message(sock)
                
                if msg and msg.get('type') == 'command':
                    t = time.localtime()
                    timestamp = f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
                    action = msg.get('action', 'UNKNOWN')
                    
                    print(f"[{timestamp}] Command: {action}")
                
        except KeyboardInterrupt:
            print("\n\nStopped by user")
            sock.close()
    else:
        print("Failed to connect to WebSocket")

print("\nProgram ended")
