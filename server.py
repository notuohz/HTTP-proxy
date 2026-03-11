"""
HTTP Proxy Server
Usage: python serv.py <PORT_NUMBER>
Example: python serv.py 8888
"""

import socket
import threading
import sys
import logging
from datetime import datetime

# set up log message format and level
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# constants with standard values
BUFFER_SIZE = 4096
DEFAULT_HTTP_PORT = 80


def parse_http_request(raw_request: bytes):
     # parse raw HTTP bytes (method, host, port, path, headers_str)
     # returns None if parsing fails
    try:
        text = raw_request.decode("utf-8", errors="ignore") # decode bytes to string, ignoring errors
        lines = text.split("\r\n") # split into lines
        request_line = lines[0] 
        parts = request_line.split(" ") # split request line into method, url, version
        if len(parts) < 3:
            return None

        method = parts[0].upper()
        url = parts[1]

        # extract host and path from URL
        if url.startswith("http://"):
            url_stripped = url[len("http://"):] # remove http:// prefix
        else:
            url_stripped = url # if no http://, treat entire URL as host

        if "/" in url_stripped:
            host_part, path = url_stripped.split("/", 1) # split into host and path
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
        for line in lines[1:]: # skip request line
            if line.lower().startswith("proxy-connection"): # ignore this header (not needed)
                continue
            header_lines.append(line) # keep all other headers as-is

        headers_str = "\r\n".join(header_lines) # rebuild headers into string for forwarding

        return method, host, port, path, headers_str

    except Exception as exc:
        log.warning(f"Failed to parse request: {exc}")
        return None


def forward_request(method: str, host: str, port: int, path: str, headers_str: str) -> bytes:
    # open a connection to host:port, send the HTTP request, and return the response

    request = f"{method} {path} HTTP/1.0\r\nHost: {host}\r\n{headers_str}\r\n\r\n" # build the HTTP request to send to server


    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as remote: # create a TCP socket to connect to server
        remote.settimeout(10) # set a timeout for the connection (to avoid hanging indefinitely)
        remote.connect((host, port)) # connect to the target server
        remote.sendall(request.encode("utf-8", errors="ignore")) # send the HTTP request to the server

        # collect full response from server
        response = b"" # stores binary data
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
    # 3. forward to server
    # 4. return response to client

    log.info(f"New connection from {client_addr}")
    try:
        # receive the full request
        raw_request = b""
        client_sock.settimeout(5)
        while True:
            chunk = client_sock.recv(BUFFER_SIZE)
            raw_request += chunk
            if len(chunk) < BUFFER_SIZE:   # no more data pending
                break

        if not raw_request:
            return

        log.info(f"Request from {client_addr}:\n{raw_request[:200].decode('utf-8', errors='ignore')}") # log the first 200 bytes of the request for debugging

        # parse the HTTP request
        parsed = parse_http_request(raw_request)
        if parsed is None:
            error_response = (
                "HTTP/1.0 400 Bad Request\r\n"
                "Content-Type: text/html\r\n\r\n"
            )
            client_sock.sendall(error_response.encode()) # if parsing failed, send a 400 Bad Request response
            return

        method, host, port, path, headers_str = parsed # unpack the parsed request components
        log.info(f"Forwarding {method} {host}:{port}{path}") # log the target server and path

        # forward & relay the request to the target server and send back the response to the client
        try:
            response = forward_request(method, host, port, path, headers_str) # forward the request to the target server and get the response
            client_sock.sendall(response) # send the server's response back to the client
            log.info(f"Sent {len(response)} bytes back to {client_addr}")

        except socket.timeout:
            error_response = ( # if connection to target server times out, send a 504 Gateway Timeout response
                "HTTP/1.0 504 Gateway Timeout\r\n"
                "Content-Type: text/html\r\n\r\n"
            )
            client_sock.sendall(error_response.encode()) # send the error response back to the client
            log.warning(f"Timeout connecting to {host}:{port}")

        except Exception as exc:
            error_response = ( # for any other exceptions when connecting to target server, send a 502 Bad Gateway response with the error message
                "HTTP/1.0 502 Bad Gateway\r\n"
                "Content-Type: text/html\r\n\r\n"
            )
            client_sock.sendall(error_response.encode())
            log.error(f"Error forwarding to {host}: {exc}")

    except Exception as exc:
        log.error(f"Unexpected error handling {client_addr}: {exc}")
    finally:
        client_sock.close()
        log.info(f"Connection closed: {client_addr}")


def start_server(port: int):
   # bind a TCP socket on port and serve clients in separate threads

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # create a TCP socket for listening to incoming client connections
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # allow reuse of address
    server_sock.bind(("", port)) # bind to all interfaces on the specified port
    server_sock.listen(10)

    log.info(f"HTTP Proxy Server listening on port {port}")
    log.info("ctrl+c to stop\n")

    try:
        while True:
            client_sock, client_addr = server_sock.accept()
            # make a new thread per client
            t = threading.Thread(
                target=handle_client,
                args=(client_sock, client_addr),
                daemon=True
            )
            t.start()
    except KeyboardInterrupt:
        log.info("Proxy server shutting down")
    finally:
        server_sock.close()


# entry point
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python server.py <PORT_NUMBER>")
        print("Example: python server.py 8888")
        sys.exit(1)

    try:
        PORT = int(sys.argv[1])
    except ValueError:
        print("Error: PORT_NUMBER must be an integer.")
        sys.exit(1)

    start_server(PORT)