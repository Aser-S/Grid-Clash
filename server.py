# We need to:
# 1. Understand GUI changes
# 2. IMPORTANT: He didnt use the delta encoding for modified
# 3. Add GAME_OVER
# 4. if delta didnt ack
# 5. timeout for ack hasnt arrived
# Delta Encoding: Changes since last snapshot, heartbeat snapshot, resending lost snapshot

import socket
import threading
import time
import struct
import json


serverPort = 12000
serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
serverSocket.bind(('', serverPort))
print(f"Server Started on port number {serverPort}")

frequency = 20
TICK_INTERVAL = 1 / frequency

clients = {}  # Track connected clients
clientNumber = 0
snapshot_id = 0

rows, cols = 10, 10
grid = [[0 for _ in range(cols)] for _ in range(rows)]
numberOfClicks = 0  # Use for checking if Game is Over

# '!4sB B I I Q H' = protocol_id, version, msg_type, snapshot_id, seq_num, timestamp, payload_len
HEADER_FORMAT = '!4s B B I I Q H'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

modifiedFlag = True  # Tracks if the grid was modified

# ======================================
# Broadcast Thread
# ======================================
def broadcast_snapshots():
    """Periodically broadcast current game state to all clients."""
    global modifiedFlag
    while True:
        for client_addr, info in list(clients.items()):
            info['last_snapshot'] += 1
            info['seq'] += 1

            # If the grid was modified and client has ACKed, send delta (msg_type=4)
            if modifiedFlag and info['last_ack']:
                snapshot_payload = json.dumps(grid).encode()
                payloadLen = len(snapshot_payload)
                snapshot_packet = struct.pack(
                    HEADER_FORMAT, b'DOMX', 1, 4, info['last_snapshot'], info['seq'],
                    int(time.time() * 1000), payloadLen
                )
                serverSocket.sendto(snapshot_packet + snapshot_payload, client_addr)
                info['last_ack'] = False

            # If grid not modified, send heartbeat (msg_type=5)
            elif not modifiedFlag:
                snapshot_packet = struct.pack(
                    HEADER_FORMAT, b'DOMX', 1, 5, info['last_snapshot'], info['seq'],
                    int(time.time() * 1000), 0
                )
                serverSocket.sendto(snapshot_packet, client_addr)

            # If client missed last ACK, send full snapshot (msg_type=3)
            elif not info['last_ack']:
                snapshot_payload = json.dumps(grid).encode()
                payloadLen = len(snapshot_payload)
                snapshot_packet = struct.pack(
                    HEADER_FORMAT, b'DOMX', 1, 3, info['last_snapshot'], info['seq'],
                    int(time.time() * 1000), payloadLen
                )
                serverSocket.sendto(snapshot_packet + snapshot_payload, client_addr)

        modifiedFlag = False
        time.sleep(TICK_INTERVAL * 10)


# Start broadcasting in a background thread
threading.Thread(target=broadcast_snapshots, daemon=True).start()


# ======================================
# Listen for Client Messages
# ======================================
while True:  # msg_type: INIT=0, ACK=1, EVENT=2, FULL=3, DELTA=4, HEARTBEAT=5
    data, clientAddress = serverSocket.recvfrom(1200)

    # Parse header
    header = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    protocol_id, version, msg_type, snap_id, seq, timestamp, payload_len = header

    # Handle INIT (client connects)
    if msg_type == 0:
        clientNumber += 1
        clients[clientAddress] = {'seq': 0, 'last_snapshot': 0, 'client number': clientNumber, 'last_ack': False}
        print(f"[INIT] Client connected: {clientAddress}, Player #{clientNumber}")
        # '!4sB B I I Q H' = protocol_id, version, msg_type, snapshot_id, seq_num, timestamp, payload_len

        # Send ACK
        response = struct.pack(HEADER_FORMAT, b'DOMX', 1, 1, 0, 0, int(time.time() * 1000), 0)
        serverSocket.sendto(response, clientAddress)

        # Send FULL snapshot (msg_type=3)
        initial_snapshot_payload = json.dumps(grid).encode()
        payloadLen = len(initial_snapshot_payload)

        clients[clientAddress]['last_snapshot'] += 1
        clients[clientAddress]['seq'] += 1

        headers = struct.pack(
            HEADER_FORMAT, b'DOMX', 1, 3,
            clients[clientAddress]['last_snapshot'],
            clients[clientAddress]['seq'],
            int(time.time() * 1000), payloadLen
        )
        serverSocket.sendto(headers + initial_snapshot_payload, clientAddress)

    # Handle ACK
    elif msg_type == 1:
        if clientAddress in clients:
            clients[clientAddress]['last_ack'] = True
            # print(f"[ACK] from {clientAddress}")

    # Handle EVENT (ACQUIRE_CELL r c)
    elif msg_type == 2:

        modifiedFlag = True
        payload = data[HEADER_SIZE:HEADER_SIZE + payload_len]
        message = payload.decode()
        print(f"[EVENT] From {clientAddress}: {message}")

        parts = message.split()
        if len(parts) == 3 and parts[0] == "ACQUIRE_CELL":
            try:
                r, c = int(parts[1]), int(parts[2])
                player_num = clients[clientAddress]['client number']
                if 0 <= r < rows and 0 <= c < cols and grid[r][c] == 0:
                    grid[r][c] = player_num
                    print(f"Cell ({r},{c}) acquired by Player {player_num}")
            except Exception as e:
                print(f"[ERROR] Invalid cell data: {e}")
