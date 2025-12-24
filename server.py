# We need to:
# 2. IMPORTANT: He didnt use the delta encoding for modified
# 3. Add GAME_OVER
# 4. if delta didnt ack
# 5. timeout for ack hasnt arrived
# Delta Encoding: Changes since last snapshot, heartbeat snapshot, resending lost snapshot

# Buffer last 3 packets and resend if no ACK received in time, we do that by writing the following code:
# work on retransmission of lost Aqcuire_CELL events
# incrementing snapshot_id for each snapshot sent

# def resend_lost_snapshots():
#     """Periodically check for unacknowledged snapshots and resend them."""
#     while not gameOver:
#         current_time = time.time() * 1000  # Current time in ms
#         for client_addr, info in list(clients.items()):
#             if not info['last_ack']:
#                 # Resend last snapshot
#                 print(f"[RESEND] Resending snapshot to {client_addr}")
#                 # [TODO] Implement the actual resend logic here
#         time.sleep(1)  # Check every second


import socket
import threading
import time
import struct
import json
import csv
import psutil
from collections import defaultdict
from datetime import datetime

serverPort = 12000
# socket.AF_INET – Address Family for IPv4. 
# socket.SOCK_DGRAM – Socket type for UDP (User Datagram Protocol).
serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# Bind the socket to the server address and port
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
gameOver = False

# Metrics tracking for CSV
metrics_data = []
client_recv_times = defaultdict(list)  # Track packet arrival times per client
client_latencies = defaultdict(list)  # Track latencies per client

# Player colors mapping (for display)
PLAYER_COLORS = {
    1: "Red", 2: "Blue", 3: "Salmon", 4: "Plum",
    5: "Purple", 6: "Orange", 7: "Pink", 8: "Cyan"
}

# '!4sB B I I Q H' = protocol_id, version, msg_type, snapshot_id, seq_num, timestamp, payload_len
HEADER_FORMAT = '!4s B B I I Q H'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

modifiedFlag = True  # Tracks if the grid was modified


# ======================================
# CSV Logging Function
# ======================================
def save_metrics_to_csv():
    """Save all collected metrics to a CSV file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"game_metrics_{timestamp}.csv"
    
    try:
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'client_id', 'snapshot_id', 'seq_num', 'server_timestamp_ms',
                'recv_time_ms', 'latency_ms', 'jitter_ms', 'perceived_position_error',
                'cpu_percent', 'bandwidth_per_client_kbps'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for row in metrics_data:
                writer.writerow(row)
        
        print(f"\n[CSV] Metrics saved to {filename}")
        return filename
    except Exception as e:
        print(f"[ERROR] Failed to save CSV: {e}")
        return None


# ======================================
# Calculate Winner and Leaderboard
# ======================================
def calculate_leaderboard():
    """Count cells owned by each player and return sorted leaderboard."""
    scores = defaultdict(int)
    
    for row in grid:
        for cell in row:
            if cell > 0:
                scores[cell] += 1
    
    # Sort by score (descending)
    leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return leaderboard


# ======================================
# Send Game Over Message
# ======================================
def broadcast_game_over():
    """Send game over message with leaderboard to all clients."""
    global gameOver
    gameOver = True
    
    leaderboard = calculate_leaderboard()
    
    # Prepare leaderboard data
    leaderboard_data = {
        "status": "GAME_OVER",
        "leaderboard": []
    }
    
    print("\n" + "="*50)
    print("GAME OVER - Final Leaderboard:")
    print("="*50)
    
    for rank, (player_id, score) in enumerate(leaderboard, 1):
        color = PLAYER_COLORS.get(player_id, f"Player{player_id}")
        print(f"{rank}. Player #{player_id} ({color}): {score} cells")
        leaderboard_data["leaderboard"].append({
            "rank": rank,
            "player_id": player_id,
            "color": color,
            "score": score
        })
    
    print("="*50 + "\n")
    
    # Broadcast to all clients (msg_type=6 for GAME_OVER)
    game_over_payload = json.dumps(leaderboard_data).encode()
    payloadLen = len(game_over_payload)
    
    for client_addr, info in list(clients.items()):
        info['seq'] += 1
        game_over_packet = struct.pack(
            HEADER_FORMAT, b'DOMX', 1, 6, 0, info['seq'],
            int(time.time() * 1000), payloadLen
        )
        serverSocket.sendto(game_over_packet + game_over_payload, client_addr)
    
    # Save metrics to CSV
    print("[SERVER] Saving metrics to CSV...")
    csv_file = save_metrics_to_csv()
    if csv_file:
        print(f"[SERVER] Game data saved successfully!")


# ======================================
# Broadcast Thread
# ======================================
def broadcast_snapshots():
    """Periodically broadcast current game state to all clients."""
    global modifiedFlag
    
    while not gameOver:
        cpu_usage = psutil.cpu_percent(interval=0)
        
        for client_addr, info in list(clients.items()):
            info['last_snapshot'] += 1
            info['seq'] += 1
            
            snapshot_time = int(time.time() * 1000)

            # Always send delta if modified (no ACK checking for retransmission)
            if modifiedFlag:
                snapshot_payload = json.dumps(grid).encode()
                payloadLen = len(snapshot_payload)
                snapshot_packet = struct.pack(
                    HEADER_FORMAT, b'DOMX', 1, 4, info['last_snapshot'], info['seq'],
                    snapshot_time, payloadLen
                )
                serverSocket.sendto(snapshot_packet + snapshot_payload, client_addr)
                bandwidth_kbps = (len(snapshot_packet) + payloadLen) * 8 / 1024 / TICK_INTERVAL

            # If grid not modified, send heartbeat (msg_type=5)
            else:
                snapshot_packet = struct.pack(
                    HEADER_FORMAT, b'DOMX', 1, 5, info['last_snapshot'], info['seq'],
                    snapshot_time, 0
                )
                serverSocket.sendto(snapshot_packet, client_addr)
                bandwidth_kbps = len(snapshot_packet) * 8 / 1024 / TICK_INTERVAL

        modifiedFlag = False
        time.sleep(TICK_INTERVAL)  # Remove the * 10 for proper 20Hz


# Start broadcasting in a background thread
threading.Thread(target=broadcast_snapshots, daemon=True).start()


# ======================================
# Listen for Client Messages
# ======================================
while True:  # msg_type: INIT=0, ACK=1, EVENT=2, FULL=3, DELTA=4, HEARTBEAT=5, GAME_OVER=6
    try:
        #[TODO] Handle game over state
        if gameOver:
            # Keep server running but stop processing new events
            time.sleep(1)
            continue
        #max 1200 bytes    
        data, clientAddress = serverSocket.recvfrom(1200)

        # Parse header
        header = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
        #[TODO] snap_id
        protocol_id, version, msg_type, snap_id, seq, timestamp, payload_len = header
        recv_time = int(time.time() * 1000)

        # Handle INIT (client connects)
        if msg_type == 0:
            clientNumber += 1
            clients[clientAddress] = {
                'seq': 0, 
                'last_snapshot': 0, 
                'client number': clientNumber, 
                'last_ack': False
            }
            print(f"[INIT] Client connected: {clientAddress}, Player #{clientNumber}")

            # Send ACK
            response = struct.pack(HEADER_FORMAT, b'DOMX', 1, 1, 0, 0, int(time.time() * 1000), 0)
            serverSocket.sendto(response, clientAddress)

            # Send FULL snapshot (msg_type=3)
            initial_snapshot_payload = json.dumps(grid).encode()
            payloadLen = len(initial_snapshot_payload)

            clients[clientAddress]['last_snapshot'] += 1
            clients[clientAddress]['seq'] += 1
            
            #TODO: lost full snapshot handling
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
                
                # Calculate latency and jitter
                latency = recv_time - timestamp
                client_latencies[clientAddress].append(latency)
                client_recv_times[clientAddress].append(recv_time)
                
                # Calculate jitter (variation in inter-arrival times)
                jitter = 0
                if len(client_recv_times[clientAddress]) >= 2:
                    inter_arrival = recv_time - client_recv_times[clientAddress][-2]
                    if len(client_recv_times[clientAddress]) >= 3:
                        prev_inter_arrival = client_recv_times[clientAddress][-2] - client_recv_times[clientAddress][-3]
                        jitter = abs(inter_arrival - prev_inter_arrival)
                
                # Store metrics
                cpu_usage = psutil.cpu_percent(interval=0)
                metrics_data.append({
                    'client_id': clients[clientAddress]['client number'],
                    'snapshot_id': snap_id,
                    'seq_num': seq,
                    'server_timestamp_ms': timestamp,
                    'recv_time_ms': recv_time,
                    'latency_ms': latency,
                    'jitter_ms': jitter,
                    'perceived_position_error': 0,  # Not applicable for grid game
                    'cpu_percent': cpu_usage,
                    'bandwidth_per_client_kbps': 0  # Will be calculated during broadcast
                })

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
                        numberOfClicks += 1
                        print(f"Cell ({r},{c}) acquired by Player {player_num}")
                        
                        # Check if game is over
                        if numberOfClicks == (rows * cols):
                            print("\n[GAME OVER] Grid is full!")
                            broadcast_game_over()
                            
                except Exception as e:
                    print(f"[ERROR] Invalid cell data: {e}")

    except OSError as e:
        # Handle connection errors gracefully (client disconnect, etc.)
        if clientAddress in clients:
            print(f"[DISCONNECT] Client {clientAddress} (Player #{clients[clientAddress]['client number']}) disconnected")
            del clients[clientAddress]
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
