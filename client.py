"""
════════════════════════════════════════════════════════
   Multi-Room Chat Client                       
                                                    
    Usage:                                             
     python client.py                                 
     python client.py --host 192.168.1.10            
     python client.py --host 192.168.1.10 --port 9000 
════════════════════════════════════════════════════════
"""

import socket
import threading
import json
import sys
import os
import time
import argparse
# ----------------------CONFIG-------------------------
DEFAULT_HOST  = "127.0.0.1"   # change to server IP for LAN play
DEFAULT_PORT  = 9000         

#  ----------------STATE--------------------------------
username      = None
current_room  = None
online_users  = []
sock          = None
running       = True
print_lock    = threading.Lock()

#  --------------------NETWORK----------------------------

def send_msg(payload: dict):
    try:
        raw = json.dumps(payload).encode("utf-8")
        sock.sendall(len(raw).to_bytes(4, "big") + raw)
    except Exception:
        pass


def recv_msg() -> dict | None:
    try:
        head = _exact(4)
        if not head:
            return None
        body = _exact(int.from_bytes(head, "big"))
        return json.loads(body.decode("utf-8")) if body else None
    except Exception:
        return None


def _exact(n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf

R   = "\033[0m"
B   = "\033[1m"
DIM = "\033[2m"
CYN = "\033[96m"
YLW = "\033[93m"
GRN = "\033[92m"
RED = "\033[91m"
BLU = "\033[94m"
PRP = "\033[95m"
WHT = "\033[97m"
ORG = "\033[33m"

#  -----------------------DISPLAY HELPERS------------------------

def tprint(text=""):
    with print_lock:
        print(text)


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def fmt_ts(ts: str) -> str:
    try:
        return ts[11:16] if "T" in ts else ts.split()[3][:5]
    except Exception:
        return ts


def header():
    tprint(CYN + B + " ══════════════════════════════════════════════════════ " + R)
    tprint(CYN + B + "    💬  Multi-Room Chat                                 " + R)
    tprint(CYN + B + " ══════════════════════════════════════════════════════ " + R)


def print_chat(msg: dict):
    ts    = fmt_ts(msg.get("timestamp", ""))
    user  = msg.get("username", "?")
    text  = msg.get("text", "")
    color = YLW if user == username else WHT
    if f"@{username}" in text:
        text = text.replace(f"@{username}", f"{RED}@{username}{R}")
    tprint(f"{DIM}[{ts}]{R} {color}{B}{user}{R}: {text}")


def print_pm(msg: dict):
    ts   = fmt_ts(msg.get("timestamp", ""))
    src  = msg.get("from", "?")
    dst  = msg.get("to", "?")
    text = msg.get("text", "")
    if msg.get("echo"):
        tprint(f"{DIM}[{ts}]{R} {PRP}{B}[PM → {dst}]{R} {text}")
    else:
        tprint(f"{DIM}[{ts}]{R} {PRP}{B}[PM ✉ {src}]{R} {text}")


def print_event(text, color=GRN):
    tprint(f"{color}  ◈ {text}{R}")


def print_error(text):
    tprint(f"{RED}  ✗  {text}{R}")


def print_info(text):
    tprint(f"{BLU}  ℹ  {text}{R}")


def print_rooms(rooms: list):
    tprint(f"\n{CYN}{B}Available Rooms:{R}")
    if not rooms:
        tprint(f"  {DIM}No rooms yet.  /create <name> to make one.{R}")
    else:
        for r in rooms:
            name    = r.get("name", "?")
            creator = r.get("creator", "?")
            count   = r.get("member_count", 0)
            lock_ic = f" {YLW}🔒{R}" if r.get("protected") else ""
            dot     = f"{GRN}●{R}" if count else f"{DIM}○{R}"
            here    = f" {CYN}← you{R}" if name == current_room else ""
            tprint(f"  {dot} {B}#{name}{R}{lock_ic}  "
                   f"{DIM}{count} member{'s' if count != 1 else ''}  "
                   f"creator: {creator}{R}{here}")
    tprint()


def print_members(room_name: str, members: dict, creator: str = ""):
    tprint(f"\n{CYN}{B}Members in #{room_name}:{R}")
    for u, joined in (members.items() if members else []):
        ts_str  = fmt_ts(joined) if joined else ""
        you_tag = f" {GRN}(you){R}" if u == username else ""
        crown   = f" {YLW}👑{R}" if u == creator else ""
        tprint(f"  {GRN}●{R} {B}{u}{R}{you_tag}{crown}  {DIM}joined {ts_str}{R}")
    tprint()


def print_online(users: list):
    tprint(f"\n{CYN}{B}Online ({len(users)}):{R}")
    for u in sorted(users, key=lambda x: x.get("username", "")):
        name = u.get("username", "?")
        room = u.get("room")
        you  = f" {GRN}(you){R}" if name == username else ""
        loc  = f"  {DIM}in #{room}{R}" if room else f"  {DIM}lobby{R}"
        tprint(f"  {GRN}●{R} {B}{name}{R}{you}{loc}")
    tprint()


def print_help():
    tprint(f"""
{CYN}{B}─ Commands ─────────────────────────────────────────{R}
{YLW}  /create <room>          {R}  Create a room (prompts password)
{YLW}  /join <room>            {R}  Join a room   (prompts password if locked)
{YLW}  /leave                  {R}  Leave current room
{YLW}  /rooms                  {R}  List all rooms
{YLW}  /members [room]         {R}  Show room members
{YLW}  /online                 {R}  Show all online users
{YLW}  /pm <user> <msg>        {R}  Private message
{YLW}  /kick <room> <user>     {R}  Kick user  (creator only)
{YLW}  /delete <room>          {R}  Delete room (creator only)
{YLW}  /clear                  {R}  Clear screen
{YLW}  /help                   {R}  Show this help
{YLW}  /quit                   {R}  Exit
{CYN}{B}────────────────────────────────────────────────────{R}
{DIM}  Tip: @username to mention someone.{R}
""")


def show_prompt():
    room_str = f"#{current_room}" if current_room else "lobby"
    with print_lock:
        sys.stdout.write(f"\r{GRN}{B}{username}{R}@{CYN}{room_str}{R} » ")
        sys.stdout.flush()


#  -----------------------RECEIVER THREAD-------------------------------

def message_receiver():
    global current_room, online_users, running

    while running:
        msg = recv_msg()
        if msg is None:
            if running:
                tprint(f"\n{RED}⚠  Connection lost.{R}")
                running = False
            break

        t = msg.get("type")

        if t == "chat_message":
            print_chat(msg)

        elif t == "private_message":
            print_pm(msg)

        elif t == "user_joined":
            print_event(f"{msg['username']} joined #{msg['room']}")

        elif t == "user_left":
            print_event(f"{msg['username']} left #{msg['room']}", DIM)

        elif t == "joined_room":
            current_room = msg["room_name"]
            clear(); header()
            lock_tag = f" {YLW}🔒{R}" if msg.get("protected") else ""
            tprint(f"\n{GRN}✓  Joined #{current_room}{lock_tag}{R}\n")
            if msg.get("members"):
                print_members(current_room, msg["members"], msg.get("creator", ""))

        elif t == "left_room":
            current_room = None
            print_event("You left the room.", YLW)

        elif t == "room_created":
            print_info(f"Room '{msg.get('room_name', '')}' created. Use /join to enter it.")

        elif t == "room_deleted":
            current_room = None
            print_event(msg.get("message", "Room was deleted."), RED)

        elif t == "kicked":
            current_room = None
            print_event(msg.get("message", "You were kicked."), RED)

        elif t == "room_list":
            print_rooms(msg.get("rooms", []))

        elif t == "room_members":
            print_members(msg.get("room_name", "?"), msg.get("members", {}), msg.get("creator", ""))

        elif t == "online_list":
            online_users = msg.get("users", [])
  
        elif t == "reaction_update":
            mid   = msg.get("message_id", "")[-6:]
            emoji = msg.get("emoji", "")
            by    = msg.get("by", "")
            tprint(f"{DIM}  [{mid}] {by} reacted {emoji}{R}")

        elif t == "error":
            print_error(msg.get("message", "Unknown error."))

        elif t == "info":
            print_info(msg.get("message", ""))

        elif t == "server_shutdown":
            tprint(f"\n{RED}{B}Server is shutting down.{R}")
            running = False
            break

        show_prompt()


#  ---------------INPUT HANDLER (maps client commands → server protocol)------------

def handle_input(line: str):

    line = line.strip()
    if not line:
        return

    # ------------------ Regular chat message ----------------
    if not line.startswith("/"):
        if not current_room:
            print_error("Join a room first  (/join <room>)")
            return
        send_msg({"type": "chat_message", "text": line})
        return

    parts = line.split()
    cmd   = parts[0].lower()

    #  /help 
    if cmd in ("/help", "/?"):
        print_help()

    # /quit 
    elif cmd in ("/quit", "/exit"):
        tprint("\nGoodbye! 👋")
        sys.exit(0)

    #  /clear 
    elif cmd == "/clear":
        clear(); header()

    #  /rooms 
    elif cmd == "/rooms":
        send_msg({"type": "list_rooms"})

    #  /online 
    elif cmd == "/online":
        print_online(online_users)

    #  /create <room>
    elif cmd == "/create":
        if len(parts) < 2:
            return print_error("Usage: /create <room_name>")
        name = parts[1]
        pwd  = input(f"  Set password for #{name} (press Enter to skip): ").strip() or None
        send_msg({"type": "create_room", "room_name": name, "password": pwd})

    #  /join <room>
    elif cmd == "/join":
        if len(parts) < 2:
            return print_error("Usage: /join <room_name>")
        name = parts[1]
        pwd  = input(f"  Password for #{name} (press Enter if open): ").strip() or None
        send_msg({"type": "join_room", "room_name": name, "password": pwd})

    # /leave 
    elif cmd == "/leave":
        send_msg({"type": "leave_room"})

    #  /members [room] 
    elif cmd == "/members":
        room = parts[1] if len(parts) > 1 else None
        send_msg({"type": "room_members", "room_name": room})

    #  /pm <user> <text…>
    elif cmd == "/pm":
        if len(parts) < 3:
            return print_error("Usage: /pm <username> <message>")
        target = parts[1]
        text   = " ".join(parts[2:])
        send_msg({"type": "private_message", "target": target, "text": text})

    # /kick <room> <user> 
    elif cmd == "/kick":
        if len(parts) < 3:
            return print_error("Usage: /kick <room> <username>")
        send_msg({"type": "kick_user", "room_name": parts[1], "target": parts[2]})

    # /delete <room> 
    elif cmd == "/delete":
        if len(parts) < 2:
            return print_error("Usage: /delete <room>")
        confirm = input(f"  Delete #{parts[1]}? This cannot be undone.  [y/N]: ").strip().lower()
        if confirm == "y":
            send_msg({"type": "delete_room", "room_name": parts[1]})

    else:
        print_error(f"Unknown command '{cmd}'.  Type /help for a list.")


#  -------------AUTH FLOW (runs before background threads start)--------------

def auth_flow():
    global username

    header()
    tprint(f"\n{CYN}👋 Welcome! Register or log in to continue.{R}")
    tprint(f"{DIM}  [l] Login    [r] Register{R}\n")

    while True:
        try:
            choice = input("  Choice » ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if choice in ("l", "login"):
            mode = "login"; break
        elif choice in ("r", "register"):
            mode = "register"; break
        else:
            print_error("Type 'l' or 'r'.")

    try:
        uname = input(f"\n  {YLW}Username{R}: ").strip()
        pwd   = input(f"  {YLW}Password{R}: ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)

    if not uname or not pwd:
        print_error("Username and password cannot be empty.")
        sys.exit(1)

    if mode == "register":
        send_msg({"type": "register", "username": uname, "password": pwd})
        res = recv_msg()
        if not res or not res.get("success"):
            print_error(res.get("message", "Registration failed.") if res else "No response.")
            sys.exit(1)
        print_info(res.get("message", ""))

    # Always send login after (or after register)
    send_msg({"type": "login", "username": uname, "password": pwd})
    res = recv_msg()
    if not res or not res.get("success"):
        print_error(res.get("message", "Login failed.") if res else "No response.")
        sys.exit(1)

    print_info(res.get("message", ""))
    username = uname

#  -----------------------------MAIN---------------------------

def main(host: str, port: int):
    global sock, running

    if os.name == "nt":
        os.system("color")
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
    except ConnectionRefusedError:
        print(f"\nCould not connect to {host}:{port} — is the server running?")
        sys.exit(1)
    except socket.gaierror:
        print(f"\nCould not resolve host '{host}'.")
        sys.exit(1)

    tprint(f"\n{GRN}Connected to {host}:{port}{R}")

    auth_flow()

    threading.Thread(target=message_receiver, daemon=True).start()

    clear(); header()
    tprint(f"\n{GRN}Logged in as {B}{username}{R}")
    tprint(f"{DIM}  /help for commands   /rooms to browse rooms{R}\n")

    while running:
        try:
            show_prompt()
            line = input()
            handle_input(line)
        except (KeyboardInterrupt, EOFError):
            tprint(f"\n{YLW}Disconnecting…{R}")
            break
        except Exception as e:
            print_error(f"Input error: {e}")

    running = False
    try:
        sock.close()
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Room Chat Client")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server IP address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    args = parser.parse_args()
    main(args.host, args.port)
