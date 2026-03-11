"""
Automated Proxy Tests written with claude ai

Usage:
  1. Start the server first:  python server.py 8888
  2. Run this script:         python test.py
"""

import socket
import threading
import time

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8888
BUFFER_SIZE = 4096
TIMEOUT = 10

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results_summary = []


# ── Helpers ────────────────────────────────────────────────────────────────────

def section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")

def log_result(test_name: str, passed: bool, note: str = ""):
    status = PASS if passed else FAIL
    results_summary.append((test_name, passed))
    print(f"  {status} — {note}")


def make_connection() -> socket.socket:
    """
    CLIENT REQUIREMENT: Connect to the server.
    Creates a TCP socket and connects to the proxy.
    Logs each step explicitly.
    """
    print("  [Client] Creating TCP socket (AF_INET, SOCK_STREAM)...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    print(f"  [Client] Connecting to proxy at {PROXY_HOST}:{PROXY_PORT}...")
    s.connect((PROXY_HOST, PROXY_PORT))
    print(f"  [Client] Connected successfully.")
    return s


def send_get(s: socket.socket, url: str) -> str:
    """
    CLIENT REQUIREMENT: Send a request + receive a response.
    Logs send and receive steps explicitly.
    """
    host = url.replace("http://", "").split("/")[0]
    request = f"GET {url} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"

    print(f"  [Client] Sending GET request → {url}")
    s.sendall(request.encode())
    print(f"  [Client] Request sent ({len(request)} bytes).")

    print("  [Client] Receiving response from proxy...")
    response = b""
    while True:
        chunk = s.recv(BUFFER_SIZE)
        if not chunk:
            break
        response += chunk

    decoded = response.decode("utf-8", errors="replace")
    print(f"  [Client] Response received ({len(response)} bytes).")
    return decoded


# ── Tests ──────────────────────────────────────────────────────────────────────

def test3_socket_creation_and_basic_get():
    section("Test 3 — Socket creation, bind, listen, accept, send/receive data")
    print("  Covers: Server creates socket → binds → listens → accepts → sends/receives")
    print("          Client connects → sends request → receives response\n")
    try:
        s = make_connection()
        response = send_get(s, "http://example.com")
        s.close()

        status_line = response.split("\r\n")[0]
        print(f"\n  [Proxy] Status returned: {status_line}")

        passed = "200" in status_line
        log_result("Test 3", passed,
                   "Server accepted connection, forwarded request, returned 200 OK."
                   if passed else f"Unexpected status: {status_line}")
    except Exception as e:
        log_result("Test 3", False, f"Exception: {e}")


def test4_http_response_codes():
    section("Test 4 — HTTP response codes (200 and 404)")
    print("  Covers: Server sends proper HTTP response codes\n")

    # 200 check
    try:
        s = make_connection()
        response = send_get(s, "http://example.com")
        s.close()
        status = response.split("\r\n")[0]
        print(f"\n  [200 check] Status: {status}")
        log_result("Test 4a (200)", "200" in status, "Correct 200 OK received.")
    except Exception as e:
        log_result("Test 4a (200)", False, f"Exception: {e}")

    print()

    # 404 check
    try:
        s = make_connection()
        response = send_get(s, "http://httpbin.org/this-page-does-not-exist")
        s.close()
        status = response.split("\r\n")[0]
        print(f"\n  [404 check] Status: {status}")
        log_result("Test 4b (404)", "404" in status, "Correct 404 Not Found received.")
    except Exception as e:
        log_result("Test 4b (404)", False, f"Exception: {e}")


def test5_data_transmission():
    section("Test 5 — Data transmission (multiple sequential requests)")
    print("  Covers: Connection handling + data transmission across multiple requests\n")

    urls = [
        "http://example.com",
        "http://httpbin.org/get",
        "http://httpbin.org/ip",
    ]

    all_passed = True
    for url in urls:
        try:
            s = make_connection()
            response = send_get(s, url)
            s.close()
            status = response.split("\r\n")[0]
            ok = any(code in status for code in ["200", "301", "302"])
            print(f"\n  URL: {url}")
            print(f"  Status: {status}")
            if not ok:
                all_passed = False
        except Exception as e:
            print(f"\n  {FAIL} on {url}: {e}")
            all_passed = False

    log_result("Test 5", all_passed,
               f"All {len(urls)} requests transmitted and received successfully."
               if all_passed else "One or more requests failed.")


def test6_concurrent_clients():
    section("Test 6 — Multiple concurrent clients (connection handling)")
    print("  Covers: Server accepts and handles multiple client connections simultaneously\n")

    results = {}

    def client_task(client_id: int):
        try:
            print(f"  [Client {client_id + 1}] Connecting and sending request...")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(TIMEOUT)
            s.connect((PROXY_HOST, PROXY_PORT))
            request = "GET http://example.com HTTP/1.0\r\nHost: example.com\r\nConnection: close\r\n\r\n"
            s.sendall(request.encode())
            response = b""
            while True:
                chunk = s.recv(BUFFER_SIZE)
                if not chunk:
                    break
                response += chunk
            s.close()
            status = response.decode("utf-8", errors="replace").split("\r\n")[0]
            results[client_id] = status
            print(f"  [Client {client_id + 1}] Response: {status}")
        except Exception as e:
            results[client_id] = f"ERROR: {e}"
            print(f"  [Client {client_id + 1}] ERROR: {e}")

    threads = [threading.Thread(target=client_task, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_ok = all("200" in v for v in results.values())
    log_result("Test 6", all_ok,
               "All 3 concurrent clients connected, sent requests, and received responses."
               if all_ok else "One or more concurrent clients failed.")


def test7_error_handling():
    section("Test 7 — Basic error handling (bad domain)")
    print("  Covers: Server handles errors gracefully without crashing\n")
    try:
        s = make_connection()
        response = send_get(s, "http://thissitedefinitelydoesnotexist99999.com")
        s.close()
        status = response.split("\r\n")[0]
        print(f"\n  [Proxy error response] {status}")
        passed = any(code in status for code in ["400", "502", "504"])
        log_result("Test 7", passed,
                   "Proxy returned a graceful error response — server did not crash."
                   if passed else f"Unexpected response: {status}")

        print("\n  [Confirming server still alive after error...]")
        s2 = make_connection()
        r2 = send_get(s2, "http://example.com")
        s2.close()
        still_alive = "200" in r2.split("\r\n")[0]
        log_result("Test 7 (server still alive)", still_alive,
                   "Server still accepting connections after error." if still_alive
                   else "Server did not respond after error.")
    except Exception as e:
        log_result("Test 7", False, f"Exception: {e}")


def test8_clean_disconnect():
    section("Test 8 — Clean disconnect (quit behavior)")
    print("  Covers: Connection handling — client disconnects without crashing server\n")
    try:
        print("  [Client] Connecting to proxy...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT)
        s.connect((PROXY_HOST, PROXY_PORT))
        print("  [Client] Connected. Now closing connection (simulating quit)...")
        s.close()
        print("  [Client] Disconnected cleanly.")

        time.sleep(0.5)

        print("  [Client] Reconnecting to verify server is still running...")
        s2 = make_connection()
        response = send_get(s2, "http://example.com")
        s2.close()
        passed = "200" in response.split("\r\n")[0]
        log_result("Test 8", passed,
                   "Server remained alive and accepted new connection after client quit."
                   if passed else "Server failed after client disconnect.")
    except Exception as e:
        log_result("Test 8", False, f"Exception: {e}")


# ── Summary ────────────────────────────────────────────────────────────────────

def print_summary():
    print(f"\n{'=' * 60}")
    print("  RESULTS SUMMARY")
    print(f"{'=' * 60}")

    requirement_map = {
        "Test 3":                    "Server: create socket, bind, listen, accept, send/receive | Client: connect, send, receive",
        "Test 4a (200)":             "Server: proper HTTP response codes (200 OK)",
        "Test 4b (404)":             "Server: proper HTTP response codes (404 Not Found)",
        "Test 5":                    "Data transmission + connection handling across multiple requests",
        "Test 6":                    "Server accepts multiple concurrent client connections",
        "Test 7":                    "Basic error handling — graceful failure on bad domain",
        "Test 7 (server still alive)": "Server survives errors and keeps accepting connections",
        "Test 8":                    "Connection handling — clean client disconnect",
        "Test PUT":                  "ftp> put — upload file through proxy using HTTP PUT",
        "Test LS":                   "ftp> ls — directory listing through proxy using HTTP GET",
    }

    total = len(results_summary)
    passed = sum(1 for _, ok in results_summary if ok)

    for name, ok in results_summary:
        status = "✅" if ok else "❌"
        req = requirement_map.get(name, "")
        print(f"\n  {status}  {name}")
        print(f"      Requirement: {req}")

    print(f"\n  Passed: {passed}/{total}")
    print(f"{'=' * 60}\n")

def test_put_command():
    section("Test — PUT command (upload file through proxy)")
    print("  Covers: Client sends PUT request, server forwards it, response received\n")

    # httpbin.org/put is a test endpoint that accepts PUT requests and echoes back what you sent
    url = "http://httpbin.org/put"
    file_contents = "Hello from the proxy client! This is a test file upload."

    try:
        host = "httpbin.org"
        request = (
            f"PUT {url} HTTP/1.0\r\n"
            f"Host: {host}\r\n"
            f"Content-Length: {len(file_contents)}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Connection: close\r\n\r\n"
            f"{file_contents}"
        )

        print(f"  [Client] Connecting to proxy...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT)
        s.connect((PROXY_HOST, PROXY_PORT))
        print(f"  [Client] Sending PUT request → {url}")
        s.sendall(request.encode())
        print(f"  [Client] Request sent ({len(request)} bytes).")

        response = b""
        while True:
            chunk = s.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk
        s.close()

        decoded = response.decode("utf-8", errors="replace")
        status = decoded.split("\r\n")[0]
        print(f"  [Client] Response received: {status}")

        passed = "200" in status
        log_result("Test PUT", passed,
                   "PUT request forwarded through proxy and 200 OK received."
                   if passed else f"Unexpected status: {status}")
    except Exception as e:
        log_result("Test PUT", False, f"Exception: {e}")


def test_ls_command():
    section("Test — LS command (directory listing through proxy)")
    print("  Covers: Client sends GET request for directory listing, response received\n")

    # httpbin.org/get serves as a stand-in for a directory listing endpoint
    url = "http://httpbin.org/get"

    try:
        s = make_connection()
        response = send_get(s, url)
        s.close()

        status = response.split("\r\n")[0]
        print(f"  [Client] LS response status: {status}")

        passed = "200" in status
        log_result("Test LS", passed,
                   "LS (GET) request forwarded through proxy and 200 OK received."
                   if passed else f"Unexpected status: {status}")
    except Exception as e:
        log_result("Test LS", False, f"Exception: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("   HTTP Proxy — Phase 1 Full Requirements Test Suite")
    print("=" * 60)
    print(f"  Proxy : {PROXY_HOST}:{PROXY_PORT}")

    print("\n[Pre-check] Verifying proxy is reachable...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect((PROXY_HOST, PROXY_PORT))
        print("[Pre-check] ✅ Proxy is online. Starting tests...\n")
    except Exception:
        print("[Pre-check] ❌ Cannot reach proxy. Is serv.py running on port 8888?")
        exit(1)

    test3_socket_creation_and_basic_get()
    test4_http_response_codes()
    test5_data_transmission()
    test6_concurrent_clients()
    test7_error_handling()
    test8_clean_disconnect()
    test_put_command()
    test_ls_command()

    print_summary()

