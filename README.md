# HTTP Proxy — Client/Server Application

A simplified FTP-style client-server application built with Python using TCP sockets. The client connects to a proxy server and supports uploading, downloading, and listing content over HTTP.

Made by:  
Alex Zhou @notuohz  
Hunter Tran @HunterTran10  
Stav Sendrovitz  @10stav  
Owen Keyser @OwenKeyser  

---

## How It Works

The server acts as an HTTP proxy — it receives requests from the client, forwards them to the target web server, and returns the response. Communication between the client and server uses raw TCP sockets.

- **Server** binds to a port, listens for connections, and handles each client in a separate thread
- **Client** connects to the server via DNS-resolved hostname or IP, and provides an interactive `ftp>` prompt

---

## Requirements

- Python 3.x
- No external libraries — standard library only

---

## Running Locally

**Start the server:**
```bash
python server.py <PORT>
```
```bash
python server.py 8888
```

**Start the client (in a separate terminal):**
```bash
python client.py <server_machine> <server_port>
```
```bash
python client.py localhost 8888
```

---

## Client Commands

Once connected, the `ftp>` prompt accepts the following commands:

| Command | Description |
|---|---|
| `get <url>` | Download a page/file from a URL through the proxy |
| `put <filename> <url>` | Upload a local file to a URL through the proxy |
| `ls <url>` | List directory contents at a URL |
| `head <url>` | Fetch only the HTTP headers for a URL |
| `quit` | Disconnect from the server and exit |

**Example session:**
```
ftp> get http://example.com
ftp> head http://example.com
ftp> put myfile.txt http://example.com/upload
ftp> ls http://example.com/
ftp> quit
```

---

## Running Tests

Make sure the server is running first, then:

```bash
python test.py
```

The test suite covers:
- Socket creation, bind, listen, accept
- HTTP response codes (200, 404)
- Data transmission across multiple requests
- Concurrent client connections
- Error handling (bad domains, timeouts)
- Clean client disconnect
- PUT and LS commands

---

## Cloud Deployment

The server is deployed on an **AWS EC2 instance** (Ubuntu, t3.micro).

**Live server:** `3.15.16.52:8888`

### Connect to the live server

1. Clone this repo:
```bash
git clone https://github.com/notuohz/HTTP-proxy.git
cd HTTP-proxy
```

2. Run the client pointed at the EC2 server:
```bash
python client.py 3.15.16.52 8888
```

3. Use the interactive prompt:
```
ftp> get http://example.com
ftp> head http://example.com
ftp> quit
```

No setup required on your end — the server is already running in the cloud.

### Deployment Details

| | |
|---|---|
| Platform | Amazon Web Services (AWS) |
| Service | EC2 (Elastic Compute Cloud) |
| Instance type | t3.micro (free tier) |
| OS | Ubuntu 22.04 |
| Port | 8888 (open to 0.0.0.0/0) |
| Server command | `python3 server.py 8888` |

---

## Project Structure

```
HTTP-proxy/
├── server.py      # Proxy server — binds, listens, forwards requests
├── client.py       # Interactive client — connects and sends commands
└── test.py      # Automated test suite
```
