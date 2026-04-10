# CN-Mini-Project

# Multi-Room Chat System

A real-time multi-user chat application built using Python socket programming and multithreading.

---

##  Features

*  User Registration & Login (persistent)
*  Multi-room chat system
*  Password-protected rooms
*  Private messaging
*  Real-time communication
*  Room admin controls (kick, delete)
*  Persistent storage (users & rooms)
*  Live server activity in terminal

---

##  Architecture

* Client-Server Model
* TCP Socket Programming
* JSON-based communication
* Multithreaded Server

---

##  Project Structure

```
server.py
client.py
users.json
rooms.json
```

---

##  How to Run

### 1. Start the Server

```
python server.py
```

### 2. Run the Client

Same Laptop
```
python client.py
```
Different Laptop (Same WiFi / LAN)
```
python client.py --host <SERVER_IP>
```


---

## 📸 Screenshots

###  Login
![Login](screenshots/Login.png)

###  Commands
![Commands](screenshots/Commands.png)

###  Chat Room
![Chat](screenshots/Chat.png)

---

##  Technologies Used

* Python
* Socket Programming
* Multithreading
* JSON

---

##  Limitations

* Works only within LAN
* No encryption implemented
* CLI-based (no GUI)

---

##  Future Enhancements

* GUI (Tkinter / Web)
* Chat history storage
* Secure communication (encryption)
* Cloud deployment

---


