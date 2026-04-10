"""
═══════════════════════════════════════════════════════
   Multi-Room Chat Server                             
                                                      
   Run:  python server.py                             
   Stop: type  stop  in the terminal                  
═══════════════════════════════════════════════════════
"""

import socket
import threading
import json
import time
import hashlib
import os

USER_DB_FILE = "users.json"
ROOMS_FILE = "rooms.json"
HOST    = "0.0.0.0"
PORT    = 9000

# ── In-memory stores ──────────────────────────────────
clients    = {}          # {username: {"sock": sock, "room": str|None}}
rooms      = {}          # {room_name: {"creator": str, "password": str|None, "members": {username: timestamp}}}
users_db   = {}          # {username: hashed_password}
lock       = threading.Lock()
running    = True
server     = None        # assigned at bottom

# ─────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────
        
def _hash(pwd: str) -> str:
    return hashlib.sha256(("chatapp_v3_" + pwd).encode()).hexdigest()

def send(sock, data: dict):
    """Encode dict → length-prefixed JSON and send."""
    try:
        raw = json.dumps(data).encode("utf-8")
        sock.sendall(len(raw).to_bytes(4, "big") + raw)
    except Exception:
        pass

def recv(sock) -> dict | None:
    """Receive a length-prefixed JSON message."""
    try:
        head = _exact(sock, 4)
        if not head:
            return None
        size = int.from_bytes(head, "big")
        if size > 10_000:
           return None
        body = _exact(sock, size)
        return json.loads(body.decode("utf-8")) if body else None
    except Exception:
        return None


def _exact(sock, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def broadcast(room: str, payload: dict, exclude: str = None):
    """Send payload to every member of a room."""
    for user, info in list(clients.items()):
        if info["room"] == room and user != exclude:
            send(info["sock"], payload)


def push_online_list():
    """Push current online-user list to all connected clients."""
    users = [{"username": u, "room": info["room"]} for u, info in clients.items()]
    payload = {"type": "online_list", "users": users}
    for info in clients.values():
        send(info["sock"], payload)


def room_list_payload() -> dict:
    return {
        "type": "room_list",
        "rooms": [
            {
                "name": name,
                "creator": data["creator"],
                "member_count": len(data["members"]),
                "protected": bool(data.get("password"))
            }
            for name, data in rooms.items()
        ]
    }

def load_users():
    global users_db
    if os.path.exists(USER_DB_FILE):
        with open(USER_DB_FILE, "r") as f:
            users_db = json.load(f)

def save_users():
    with open(USER_DB_FILE, "w") as f:
        json.dump(users_db, f)
        
def load_rooms():
    global rooms
    if os.path.exists(ROOMS_FILE):
        with open(ROOMS_FILE, "r") as f:
            rooms = json.load(f)

        for room in rooms:
            rooms[room]["members"] = {}

def save_rooms():
    with open(ROOMS_FILE, "w") as f:
        json.dump(rooms, f)
        
# ─────────────────────────────────────────────────────
#  SHUTDOWN
# ─────────────────────────────────────────────────────

def shutdown():
    global running
    running = False
    print("\n🛑  Shutting down…")
    for info in list(clients.values()):
        try:
            send(info["sock"], {"type": "server_shutdown"})
            info["sock"].close()
        except Exception:
            pass
    try:
        server.close()
    except Exception:
        pass


def console_watcher():
    """Allow operator to type 'stop' to gracefully halt the server."""
    while True:
        if input().strip().lower() in ("stop", "quit", "exit"):
            shutdown()
            break

# ─────────────────────────────────────────────────────
#  CLIENT THREAD
# ─────────────────────────────────────────────────────

def client_thread(sock):
    username = None
    try:
        username = _auth(sock)
        if not username:
            return
        _session(sock, username)
    finally:
        with lock:
            if username and username in clients:
                room = clients[username]["room"]

                if room and room in rooms:
                    rooms[room]["members"].pop(username, None)
                    broadcast(room, {"type": "user_left", "username": username, "room": room})

                print(f"[{time.strftime('%H:%M:%S')}] {username} disconnected")
                
                del clients[username]
        push_online_list()
        try:
            sock.close()
        except Exception:
            pass


def _auth(sock) -> str | None:
    """Handle register + login sequence; return username or None."""
    msg = recv(sock)
    if not msg:
        return None

    # Optional registration step
    if msg.get("type") == "register":
        uname = msg.get("username", "").strip()
        pwd   = msg.get("password", "")
        if not uname or not pwd:
            send(sock, {"type": "auth_result", "success": False, "message": "Username/password required."})
            return None
        if uname in users_db:
            send(sock, {"type": "auth_result", "success": False, "message": "Username already taken."})
            return None
        users_db[uname] = _hash(pwd)
        save_users()
        print(f"[{time.strftime('%H:%M:%S')}] {uname} registered")
        send(sock, {"type": "auth_result", "success": True, "message": "Registered! Please log in."})
        msg = recv(sock)  # expect login next
        if not msg:
            return None

    # Login
    if msg.get("type") == "login":
        uname = msg.get("username", "").strip()
        pwd   = msg.get("password", "")
        if users_db.get(uname) != _hash(pwd):
            send(sock, {"type": "auth_result", "success": False, "message": "Invalid credentials."})
            return None
        if uname in clients:
            send(sock, {"type": "auth_result", "success": False, "message": "Already logged in elsewhere."})
            return None
        send(sock, {"type": "auth_result", "success": True, "message": f"Welcome back, {uname}!"})
        print(f"[{time.strftime('%H:%M:%S')}] {uname} logged in")
        with lock:
            clients[uname] = {"sock": sock, "room": None}
        # Send initial state
        send(sock, room_list_payload())
        push_online_list()
        return uname

    return None


def _session(sock, username: str):
    """Main message loop for an authenticated client."""
    while running:
        msg = recv(sock)
        if not msg:
            break

        t = msg.get("type", "")

        # ── CREATE ROOM ──────────────────────────────
        if t == "create_room":
            name = msg.get("room_name", "").strip()
            pwd  = msg.get("password") or None
            if not name:
                send(sock, {"type": "error", "message": "Room name cannot be empty."}); continue
            with lock:
                if name in rooms:
                    send(sock, {"type": "error", "message": f"Room '{name}' already exists."}); continue
                rooms[name] = {"creator": username, "password": pwd, "members": {}}
                save_rooms()
            send(sock, {"type": "room_created", "room_name": name})
            # broadcast updated room list to everyone
            rl = room_list_payload()
            for info in clients.values():
                send(info["sock"], rl)

        # ── JOIN ROOM ────────────────────────────────
        elif t == "join_room":
            name = msg.get("room_name", "").strip()
            pwd  = msg.get("password") or None
            if clients[username]["room"] == name:
                send(sock, {"type": "error", "message": "You are already in this room."})
                continue
            if name not in rooms:
                send(sock, {"type": "error", "message": f"Room '{name}' does not exist."}); continue
            room_data = rooms[name]
            if room_data["password"] and room_data["password"] != pwd:
                send(sock, {"type": "error", "message": "Wrong password."}); continue
            # Leave old room first
            old = clients[username]["room"]
            if old and old in rooms:
                rooms[old]["members"].pop(username, None)
                broadcast(old, {"type": "user_left", "username": username, "room": old})
            with lock:
                clients[username]["room"] = name
                rooms[name]["members"][username] = time.strftime("%Y-%m-%dT%H:%M:%S")
                save_rooms()
            send(sock, {
                "type": "joined_room",
                "room_name": name,
                "members": rooms[name]["members"],
                "creator": rooms[name]["creator"],
                "protected": bool(rooms[name]["password"])
            })
            broadcast(name, {"type": "user_joined", "username": username, "room": name}, exclude=username)
            push_online_list()

        # ── LEAVE ROOM ───────────────────────────────
        elif t == "leave_room":
            room = clients[username]["room"]
            if room and room in rooms:
                with lock:
                    if room in rooms:
                        rooms[room]["members"].pop(username, None)
                        clients[username]["room"] = None
                        save_rooms()
                send(sock, {"type": "left_room"})
                broadcast(room, {"type": "user_left", "username": username, "room": room})
                push_online_list()

        # ── CHAT MESSAGE ─────────────────────────────
        elif t == "chat_message":
            room = clients[username]["room"]
            if not room:
                send(sock, {"type": "error", "message": "You are not in a room."}); continue
            payload = {
                "type": "chat_message",
                "id": f"{time.time():.6f}",
                "username": username,
                "text": msg.get("text", ""),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
            broadcast(room, payload)   # sender also receives own message via broadcast

        # ── TYPING INDICATOR ─────────────────────────
        elif t == "typing":
            room = clients[username]["room"]
            if room:
                broadcast(room, {"type": "typing", "username": username}, exclude=username)

        # ── PRIVATE MESSAGE ──────────────────────────
        elif t == "private_message":
            target = msg.get("target", "")
            text   = msg.get("text", "")
            if target not in clients:
                send(sock, {"type": "error", "message": f"'{target}' is not online."}); continue
            pm = {
                "type": "private_message",
                "from": username,
                "to": target,
                "text": text,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
            send(clients[target]["sock"], pm)
            pm["echo"] = True
            send(sock, pm)

        # ── KICK USER ────────────────────────────────
        elif t == "kick_user":
            room   = msg.get("room_name", "")
            target = msg.get("target", "")
            
            if room not in rooms:
                send(sock, {"type": "error", "message": "Room not found."})
                continue

            if rooms[room]["creator"] != username:
                send(sock, {"type": "error", "message": "Only the room creator can kick."})
                continue

            if target not in rooms[room]["members"]:
                send(sock, {"type": "error", "message": f"'{target}' is not in the room."})
                continue

            with lock:
                rooms[room]["members"].pop(target, None)
                save_rooms()
                if target in clients:
                    clients[target]["room"] = None
                    send(clients[target]["sock"], {
                        "type": "kicked",
                        "message": f"You were kicked from '{room}'."
                    })

            broadcast(room, {"type": "user_left", "username": target, "room": room})
            push_online_list()

        # ── DELETE ROOM ──────────────────────────────
        elif t == "delete_room":
            room = msg.get("room_name", "")
            if room not in rooms:
                send(sock, {"type": "error", "message": "Room not found."}); continue
            if rooms[room]["creator"] != username:
                send(sock, {"type": "error", "message": "Only the room creator can delete."}); continue
            # Notify all members
            for member in list(rooms[room]["members"].keys()):
                if member in clients:
                    send(clients[member]["sock"], {"type": "room_deleted", "message": f"Room '{room}' was deleted by its creator."})
                    with lock:
                        clients[member]["room"] = None            
            del rooms[room]
            save_rooms()
            rl = room_list_payload()
            for info in clients.values():
                send(info["sock"], rl)

        # ── LIST ROOMS ───────────────────────────────
        elif t == "list_rooms":
            send(sock, room_list_payload())

        # ── ROOM MEMBERS ─────────────────────────────
        elif t == "room_members":
            room = msg.get("room_name") or clients[username]["room"]
            if not room or room not in rooms:
                send(sock, {"type": "error", "message": "Room not found."}); continue
            send(sock, {
                "type": "room_members",
                "room_name": room,
                "members": rooms[room]["members"],
                "creator": rooms[room]["creator"]
            })

        # ── REACTION ─────────────────────────────────
        elif t == "reaction":
            room = clients[username]["room"]
            if not room:
                continue
            broadcast(room, {
                "type": "reaction_update",
                "message_id": msg.get("message_id", ""),
                "emoji": msg.get("emoji", ""),
                "by": username
            })

# ─────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────

load_users()
load_rooms()

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen()
server.settimeout(1)


print(f"🚀  Server running on {HOST}:{PORT}")
print("    Type  stop  to shut down.\n")

threading.Thread(target=console_watcher, daemon=True).start()

while running:
    try:
        conn, addr = server.accept()
        threading.Thread(target=client_thread, args=(conn,), daemon=True).start()
    except socket.timeout:
        continue
    except Exception:
        break

print("✅  Server stopped.")
