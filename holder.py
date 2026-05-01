"""
HTTP Proxy Server
Usage: python serv.py <PORT_NUMBER>
Example: python serv.py 8888
"""

import socket
import threading
import sys
import logging

# set up log message format and level
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("proxy.log")
    ]
)
log = logging.getLogger(__name__)

# constants with standard values
BUFFER_SIZE = 4096
DEFAULT_HTTP_PORT = 80


def parse_http_request(raw_request: bytes):
    # parse raw HTTP bytes into (method, host, port, path, headers_str)
    # returns None if parsing fails
    try:
        text = raw_request.decode("utf-8", errors="ignore")
        lines = text.split("\r\n")
        request_line = lines[0]
        parts = request_line.split(" ")
        if len(parts) < 3:
            return None

        method = parts[0].upper()
        url = parts[1]

        # extract host and path from URL
        if url.startswith("http://"):
            url_stripped = url[len("http://"):]
        else:
            url_stripped = url

        if "/" in url_stripped:
            host_part, path = url_stripped.split("/", 1)
            path = "/" + path
        else:
            host_part = url_stripped
            path = "/"

        # extract port from host if present
        if ":" in host_part:
            host, port = host_part.split(":", 1)
            port = int(port)
        else:
            host = host_part
            port = DEFAULT_HTTP_PORT

        # rebuild headers, excluding proxy-connection
        header_lines = []
        for line in lines[1:]:
            if line.lower().startswith("proxy-connection"):
                continue
            header_lines.append(line)

        headers_str = "\r\n".join(header_lines)

        return method, host, port, path, headers_str

    except Exception as exc:
        log.warning(f"Failed to parse request: {exc}")
        return None


def forward_request(method: str, host: str, port: int, path: str, headers_str: str) -> bytes:
    # open a connection to host:port, send the HTTP request, and return the response
    request = f"{method} {path} HTTP/1.0\r\nHost: {host}\r\n{headers_str}\r\n\r\n"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as remote:
        remote.settimeout(10)
        remote.connect((host, port))
        remote.sendall(request.encode("utf-8", errors="ignore"))

        response = b""
        while True:
            chunk = remote.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk

    return response


def handle_client(client_sock: socket.socket, client_addr):
    # handle one client connection:
    # 1. receive the HTTP request
    # 2. parse it
    # 3. forward to target server
    # 4. return response to client
    log.info(f"New connection from {client_addr}")
    try:
        # receive the full request — use timeout so we don't hang on empty/slow clients
        raw_request = b""
        client_sock.settimeout(5)
        try:
            while True:
                chunk = client_sock.recv(BUFFER_SIZE)
                if not chunk:
                    break  # client closed connection
                raw_request += chunk
                if len(chunk) < BUFFER_SIZE:
                    break  # no more data pending
        except socket.timeout:
            pass  # partial request received — attempt to parse what we have

        if not raw_request:
            return

        log.info(f"Request from {client_addr}:\n{raw_request[:200].decode('utf-8', errors='ignore')}")

        # parse the HTTP request
        parsed = parse_http_request(raw_request)
        if parsed is None:
            client_sock.sendall(b"HTTP/1.0 400 Bad Request\r\nContent-Type: text/html\r\n\r\n")
            return

        method, host, port, path, headers_str = parsed
        log.info(f"Forwarding {method} {host}:{port}{path}")

        # forward to target server and relay response back to client
        try:
            response = forward_request(method, host, port, path, headers_str)
            client_sock.sendall(response)
            log.info(f"Sent {len(response)} bytes back to {client_addr}")

        except socket.timeout:
            client_sock.sendall(b"HTTP/1.0 504 Gateway Timeout\r\nContent-Type: text/html\r\n\r\n")
            log.warning(f"Timeout connecting to {host}:{port}")

        except Exception as exc:
            client_sock.sendall(b"HTTP/1.0 502 Bad Gateway\r\nContent-Type: text/html\r\n\r\n")
            log.error(f"Error forwarding to {host}: {exc}")

    except Exception as exc:
        log.error(f"Unexpected error handling {client_addr}: {exc}")
    finally:
        client_sock.close()
        log.info(f"Connection closed: {client_addr}")


def start_server(port: int):
    # bind a TCP socket on port and serve clients in separate threads
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("", port))
    server_sock.listen(10)

    # set a timeout on accept() so KeyboardInterrupt (Ctrl+C) can fire between accepts
    server_sock.settimeout(1.0)

    log.info(f"HTTP Proxy Server listening on port {port}")
    log.info("Ctrl+C to stop\n")

    try:
        while True:
            try:
                client_sock, client_addr = server_sock.accept()
                t = threading.Thread(
                    target=handle_client,
                    args=(client_sock, client_addr),
                    daemon=True
                )
                t.start()
            except socket.timeout:
                pass  # no connection in the last second — loop back and check for Ctrl+C
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Proxy server shutting down")
        server_sock.close()


# entry point
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python serv.py <PORT_NUMBER>")
        print("Example: python serv.py 8888")
        sys.exit(1)

    try:
        PORT = int(sys.argv[1])
    except ValueError:
        print("Error: PORT_NUMBER must be an integer.")
        sys.exit(1)

    start_server(PORT)