"""
HTTP Proxy Server - Phase 2-ready version
Usage: python server.py <PORT_NUMBER> [AUTH_TOKEN]
Example: python server.py 8888 mySecretToken

New Phase 2 features added:
1. Token-based authentication using X-Proxy-Auth header
2. Server status / monitoring endpoint
3. blocked_sites.txt security filtering
"""

import socket
import threading
import sys
import logging
import os
import time
from datetime import datetime

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
BLOCKLIST_FILE = "blocked_sites.txt"
DEFAULT_AUTH_TOKEN = "phase2token"

# server-wide monitoring stats
stats_lock = threading.Lock()
server_stats = {
    "start_time": time.time(),
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "blocked_requests": 0,
    "auth_failures": 0,
    "active_clients": 0,
}

# authentication token is configured when the server starts
AUTH_TOKEN = DEFAULT_AUTH_TOKEN


def update_stat(key: str, amount: int = 1):
    """Safely update one server statistic from any client thread."""
    with stats_lock:
        server_stats[key] += amount


def format_uptime(seconds: float) -> str:
    """Convert uptime seconds into HH:MM:SS format."""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_http_response(status_code: int, reason: str, body: str, content_type: str = "text/plain") -> bytes:
    """Build a simple HTTP response for proxy-generated messages."""
    body_bytes = body.encode("utf-8", errors="replace")
    response = (
        f"HTTP/1.0 {status_code} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("utf-8") + body_bytes
    return response


def load_blocked_sites() -> set:
    """Load blocked domains from blocked_sites.txt, ignoring comments and blank lines."""
    blocked = set()
    if not os.path.exists(BLOCKLIST_FILE):
        return blocked

    with open(BLOCKLIST_FILE, "r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            site = line.strip().lower()
            if not site or site.startswith("#"):
                continue
            site = site.replace("http://", "").replace("https://", "")
            site = site.split("/")[0].split(":")[0]
            blocked.add(site)
    return blocked


def is_blocked(host: str, blocked_sites: set) -> bool:
    """Return True when host matches a blocked domain or one of its subdomains."""
    host = host.lower().strip()
    for blocked in blocked_sites:
        if host == blocked or host.endswith("." + blocked):
            return True
    return False


def extract_header(headers_str: str, header_name: str) -> str:
    """Extract one HTTP header value from a header string."""
    wanted = header_name.lower()
    for line in headers_str.split("\r\n"):
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        if name.strip().lower() == wanted:
            return value.strip()
    return ""


def remove_proxy_auth_header(headers_str: str) -> str:
    """Remove X-Proxy-Auth before forwarding the request to the outside website."""
    safe_headers = []
    for line in headers_str.split("\r\n"):
        if line.lower().startswith("x-proxy-auth:"):
            continue
        safe_headers.append(line)
    return "\r\n".join(safe_headers)


def is_authenticated(headers_str: str) -> bool:
    """Check whether the client supplied the correct X-Proxy-Auth token."""
    supplied_token = extract_header(headers_str, "X-Proxy-Auth")
    return supplied_token == AUTH_TOKEN


def build_status_response(client_addr) -> bytes:
    """Build a live status/monitoring response for the custom client status command."""
    with stats_lock:
        uptime = format_uptime(time.time() - server_stats["start_time"])
        body = (
            "Proxy Server Status\n"
            "===================\n"
            f"Server time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Uptime: {uptime}\n"
            f"Total requests: {server_stats['total_requests']}\n"
            f"Successful requests: {server_stats['successful_requests']}\n"
            f"Failed requests: {server_stats['failed_requests']}\n"
            f"Blocked requests: {server_stats['blocked_requests']}\n"
            f"Authentication failures: {server_stats['auth_failures']}\n"
            f"Active clients: {server_stats['active_clients']}\n"
            f"Current client: {client_addr[0]}:{client_addr[1]}\n"
        )
    return build_http_response(200, "OK", body)


def parse_http_request(raw_request: bytes):
    # parse raw HTTP bytes (method, host, port, path, headers_str)
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

        # custom local command used by client.py status
        if method == "STATUS":
            header_lines = lines[1:]
            headers_str = "\r\n".join(header_lines)
            return method, "proxy-status", DEFAULT_HTTP_PORT, "/status", headers_str

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

    headers_str = remove_proxy_auth_header(headers_str)
    request = f"{method} {path} HTTP/1.0\r\nHost: {host}\r\n{headers_str}\r\n\r\n"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as remote:
        remote.settimeout(10)
        remote.connect((host, port))
        remote.sendall(request.encode("utf-8", errors="ignore"))

        # collect full response from server
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
    # 2. authenticate the request
    # 3. check status/blocklist/normal proxy forwarding
    # 4. return response to client

    log.info(f"New connection from {client_addr}")
    update_stat("active_clients", 1)

    try:
        # receive the full request
        raw_request = b""
        client_sock.settimeout(5)
        while True:
            chunk = client_sock.recv(BUFFER_SIZE)
            raw_request += chunk
            if len(chunk) < BUFFER_SIZE:
                break

        if not raw_request:
            return

        update_stat("total_requests")
        log.info(f"Request from {client_addr}:\n{raw_request[:200].decode('utf-8', errors='ignore')}")

        # parse the HTTP request
        parsed = parse_http_request(raw_request)
        if parsed is None:
            update_stat("failed_requests")
            client_sock.sendall(build_http_response(400, "Bad Request", "400 Bad Request: could not parse request."))
            return

        method, host, port, path, headers_str = parsed

        # authentication check for every client command/request
        if not is_authenticated(headers_str):
            update_stat("failed_requests")
            update_stat("auth_failures")
            log.warning(f"Authentication failed from {client_addr}")
            client_sock.sendall(build_http_response(401, "Unauthorized", "401 Unauthorized: invalid or missing proxy authentication token."))
            return

        # custom status command, not forwarded to an outside website
        if method == "STATUS":
            response = build_status_response(client_addr)
            client_sock.sendall(response)
            update_stat("successful_requests")
            log.info(f"Returned status report to {client_addr}")
            return

        # security blocklist check
        blocked_sites = load_blocked_sites()
        if is_blocked(host, blocked_sites):
            update_stat("failed_requests")
            update_stat("blocked_requests")
            log.warning(f"Blocked request from {client_addr} to {host}")
            body = f"403 Forbidden: access to '{host}' is blocked by proxy policy."
            client_sock.sendall(build_http_response(403, "Forbidden", body))
            return

        log.info(f"Forwarding {method} {host}:{port}{path}")

        # forward & relay the request to the target server and send back the response to the client
        try:
            response = forward_request(method, host, port, path, headers_str)
            client_sock.sendall(response)
            update_stat("successful_requests")
            log.info(f"Sent {len(response)} bytes back to {client_addr}")

        except socket.timeout:
            update_stat("failed_requests")
            client_sock.sendall(build_http_response(504, "Gateway Timeout", "504 Gateway Timeout: target server did not respond."))
            log.warning(f"Timeout connecting to {host}:{port}")

        except Exception as exc:
            update_stat("failed_requests")
            client_sock.sendall(build_http_response(502, "Bad Gateway", f"502 Bad Gateway: {exc}"))
            log.error(f"Error forwarding to {host}: {exc}")

    except Exception as exc:
        update_stat("failed_requests")
        log.error(f"Unexpected error handling {client_addr}: {exc}")
    finally:
        update_stat("active_clients", -1)
        client_sock.close()
        log.info(f"Connection closed: {client_addr}")


def start_server(port: int, auth_token: str):
    # bind a TCP socket on port and serve clients in separate threads
    global AUTH_TOKEN
    AUTH_TOKEN = auth_token

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("", port))
    server_sock.listen(10)
    server_sock.settimeout(1)  # to allow periodic check for Ctrl+C

    log.info(f"HTTP Proxy Server listening on port {port}")
    log.info("Phase 2 features enabled: authentication, status monitoring, blocklist filtering")
    log.info(f"Authentication token configured. Clients must send X-Proxy-Auth header.")
    log.info(f"Blocklist file: {BLOCKLIST_FILE}")
    log.info("ctrl+c to stop\n")

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
                pass
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Proxy server shutting down")
        server_sock.close()


# entry point
if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Usage: python server.py <PORT_NUMBER> [AUTH_TOKEN]")
        print("Example: python server.py 8888 mySecretToken")
        sys.exit(1)

    try:
        PORT = int(sys.argv[1])
    except ValueError:
        print("Error: PORT_NUMBER must be an integer.")
        sys.exit(1)

    token = sys.argv[2] if len(sys.argv) == 3 else os.environ.get("PROXY_AUTH_TOKEN", DEFAULT_AUTH_TOKEN)
    start_server(PORT, token)
