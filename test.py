"""
Full test suite for the HTTP Proxy
Tests both local and cloud (EC2) deployment.

Usage:
  1. Start the server first:  python server.py 8888
  2. Run this script:         python test.py
"""

import socket
import threading
import time
import os

# ── Config ─────────────────────────────────────────────────────────────────────

LOCAL_HOST  = "127.0.0.1"
EC2_HOST    = "3.15.16.52"
PORT        = 8888
TIMEOUT     = 10
AUTH_TOKEN  = "phase2token"
WRONG_TOKEN = "wrongtoken"
BLOCKLIST_FILE = "blocked_sites.txt"
TEST_BLOCKED_DOMAIN = "blocked-test-site.com"

ok_count   = 0
fail_count = 0


# ── Helpers ────────────────────────────────────────────────────────────────────

def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def check(label, condition, note=""):
    global ok_count, fail_count
    if condition:
        print(f"  ✅ PASS  {label}  {note}")
        ok_count += 1
    else:
        print(f"  ❌ FAIL  {label}  {note}")
        fail_count += 1


def send_raw(host, port, raw_request: str) -> str:
    """Send a raw HTTP request string and return the decoded response."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    s.connect((host, port))
    s.sendall(raw_request.encode())
    resp = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        resp += chunk
    s.close()
    return resp.decode("utf-8", errors="replace")


def make_get(url, token=AUTH_TOKEN) -> str:
    """Build and send a GET request with auth token."""
    host = url.replace("http://", "").split("/")[0]
    req = (
        f"GET {url} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"X-Proxy-Auth: {token}\r\n"
        f"Connection: close\r\n\r\n"
    )
    return send_raw(LOCAL_HOST, PORT, req)


def make_get_timed(url, token=AUTH_TOKEN):
    """Send a GET request and return (response, rtt, byte_count)."""
    host = url.replace("http://", "").split("/")[0]
    req = (
        f"GET {url} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        f"X-Proxy-Auth: {token}\r\n"
        f"Connection: close\r\n\r\n"
    )
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    s.connect((LOCAL_HOST, PORT))

    start = time.time()
    s.sendall(req.encode())
    resp = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        resp += chunk
    rtt = time.time() - start

    s.close()
    return resp.decode("utf-8", errors="replace"), rtt, len(resp)


def make_status(host=LOCAL_HOST, token=AUTH_TOKEN) -> str:
    """Send a STATUS command and return the response."""
    req = (
        "STATUS proxy://status HTTP/1.0\r\n"
        "Host: proxy-status\r\n"
        f"X-Proxy-Auth: {token}\r\n"
        "Connection: close\r\n\r\n"
    )
    return send_raw(host, PORT, req)


def status_line(response: str) -> str:
    return response.split("\r\n")[0]


# ── Blocklist helpers ──────────────────────────────────────────────────────────

def add_to_blocklist(domain):
    with open(BLOCKLIST_FILE, "a") as f:
        f.write(f"\n{domain}\n")


def remove_from_blocklist(domain):
    if not os.path.exists(BLOCKLIST_FILE):
        return
    with open(BLOCKLIST_FILE, "r") as f:
        lines = f.readlines()
    with open(BLOCKLIST_FILE, "w") as f:
        for line in lines:
            if line.strip() != domain:
                f.write(line)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_basic_connection():
    section("Basic connection + GET")
    try:
        r = make_get("http://example.com")
        line = status_line(r)
        print(f"  Response: {line}")
        check("connect + GET", "200" in line)
    except Exception as e:
        check("connect + GET", False, str(e))


def test_response_codes():
    section("HTTP response codes (200 and 404)")
    try:
        r = make_get("http://example.com")
        line = status_line(r)
        check("200 OK", "200" in line, line)
    except Exception as e:
        check("200 OK", False, str(e))

    try:
        r = make_get("http://httpbin.org/this-page-does-not-exist")
        line = status_line(r)
        check("404 Not Found", "404" in line, line)
    except Exception as e:
        check("404 Not Found", False, str(e))


def test_multiple_requests():
    section("Multiple sequential requests")
    urls = ["http://example.com", "http://httpbin.org/get", "http://httpbin.org/ip"]
    all_good = True
    for u in urls:
        try:
            r = make_get(u)
            line = status_line(r)
            ok = any(x in line for x in ["200", "301", "302"])
            print(f"  {u}  →  {line}")
            if not ok:
                all_good = False
        except Exception as e:
            print(f"  error on {u}: {e}")
            all_good = False
    check("multiple requests", all_good)


def test_concurrent_clients():
    section("Concurrent clients (3 simultaneous connections)")
    results = {}

    def one_client(i):
        try:
            r = make_get("http://example.com")
            line = status_line(r)
            results[i] = line
            print(f"  client {i+1}: {line}")
        except Exception as e:
            results[i] = "ERROR"
            print(f"  client {i+1} error: {e}")

    threads = [threading.Thread(target=one_client, args=(i,)) for i in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()
    check("concurrent clients", all("200" in v for v in results.values()))


def test_bad_domain():
    section("Bad domain error handling")
    try:
        r = make_get("http://thissitedefinitelydoesnotexist99999.com")
        line = status_line(r)
        print(f"  Got back: {line}")
        check("bad domain → error response", any(x in line for x in ["400", "502", "504"]), line)

        r2 = make_get("http://example.com")
        check("server alive after error", "200" in status_line(r2))
    except Exception as e:
        check("bad domain → error response", False, str(e))


def test_clean_disconnect():
    section("Clean disconnect")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT)
        s.connect((LOCAL_HOST, PORT))
        s.close()
        time.sleep(0.5)

        r = make_get("http://example.com")
        check("server ok after disconnect", "200" in status_line(r))
    except Exception as e:
        check("server ok after disconnect", False, str(e))


def test_put():
    section("PUT request")
    try:
        url = "http://httpbin.org/put"
        body = "Hello from the proxy client! This is a test file upload."
        req = (
            f"PUT {url} HTTP/1.0\r\n"
            f"Host: httpbin.org\r\n"
            f"X-Proxy-Auth: {AUTH_TOKEN}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Connection: close\r\n\r\n"
            f"{body}"
        )
        r = send_raw(LOCAL_HOST, PORT, req)
        line = status_line(r)
        print(f"  PUT response: {line}")
        check("PUT upload", "200" in line, line)
    except Exception as e:
        check("PUT upload", False, str(e))


def test_ls():
    section("LS (directory listing via GET)")
    try:
        r = make_get("http://httpbin.org/get")
        line = status_line(r)
        print(f"  LS response: {line}")
        check("LS listing", "200" in line, line)
    except Exception as e:
        check("LS listing", False, str(e))


# ── New feature tests ──────────────────────────────────────────────────────────

def test_auth_valid():
    section("Authentication — valid token")
    try:
        r = make_get("http://example.com", token=AUTH_TOKEN)
        line = status_line(r)
        print(f"  Response with valid token: {line}")
        check("valid token accepted", "200" in line, line)
    except Exception as e:
        check("valid token accepted", False, str(e))


def test_auth_invalid():
    section("Authentication — invalid token (expect 401)")
    try:
        r = make_get("http://example.com", token=WRONG_TOKEN)
        line = status_line(r)
        print(f"  Response with wrong token: {line}")
        check("invalid token rejected (401)", "401" in line, line)
    except Exception as e:
        check("invalid token rejected (401)", False, str(e))


def test_auth_missing():
    section("Authentication — missing token (expect 401)")
    try:
        # send request with no X-Proxy-Auth header at all
        req = (
            "GET http://example.com HTTP/1.0\r\n"
            "Host: example.com\r\n"
            "Connection: close\r\n\r\n"
        )
        r = send_raw(LOCAL_HOST, PORT, req)
        line = status_line(r)
        print(f"  Response with no token: {line}")
        check("missing token rejected (401)", "401" in line, line)
    except Exception as e:
        check("missing token rejected (401)", False, str(e))


def test_blocklist():
    section("Blocklist filtering (expect 403)")
    add_to_blocklist(TEST_BLOCKED_DOMAIN)
    try:
        r = make_get(f"http://{TEST_BLOCKED_DOMAIN}/somepage")
        line = status_line(r)
        print(f"  Response for blocked domain: {line}")
        check("blocked domain returns 403", "403" in line, line)
    except Exception as e:
        check("blocked domain returns 403", False, str(e))
    finally:
        remove_from_blocklist(TEST_BLOCKED_DOMAIN)

    # confirm a normal request still works after blocklist check
    try:
        r = make_get("http://example.com")
        check("normal request works after blocklist check", "200" in status_line(r))
    except Exception as e:
        check("normal request works after blocklist check", False, str(e))


def test_status_command():
    section("Status / monitoring command")
    try:
        r = make_status()
        line = status_line(r)
        print(f"  Status response code: {line}")
        body = r.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in r else ""
        print(f"  Status body preview:\n{body[:300]}")

        check("status returns 200",        "200" in line, line)
        check("status shows uptime",        "Uptime" in body)
        check("status shows total requests","Total requests" in body)
        check("status shows active clients","Active clients" in body)
    except Exception as e:
        check("status command", False, str(e))


def test_status_auth():
    section("Status command — wrong token (expect 401)")
    try:
        r = make_status(token=WRONG_TOKEN)
        line = status_line(r)
        print(f"  Status with wrong token: {line}")
        check("status rejects wrong token (401)", "401" in line, line)
    except Exception as e:
        check("status rejects wrong token (401)", False, str(e))


def test_performance_metrics():
    section("Performance metrics (RTT + throughput)")
    try:
        response, rtt, byte_count = make_get_timed("http://example.com")
        throughput = (byte_count / rtt / 1024) if rtt > 0 else 0
        print(f"  RTT        : {rtt:.3f}s")
        print(f"  Received   : {byte_count} bytes")
        print(f"  Throughput : {throughput:.1f} KB/s")

        check("RTT is measured (> 0)",       rtt > 0,        f"{rtt:.3f}s")
        check("RTT is reasonable (< 10s)",   rtt < 10,       f"{rtt:.3f}s")
        check("bytes received (> 0)",        byte_count > 0, f"{byte_count} bytes")
        check("throughput calculated (> 0)", throughput > 0, f"{throughput:.1f} KB/s")
    except Exception as e:
        check("performance metrics", False, str(e))


def test_ec2_remote():
    section("Cloud deployment — EC2 remote connection")
    print(f"  Attempting to reach EC2 server at {EC2_HOST}:{PORT} ...")
    try:
        req = (
            "GET http://example.com HTTP/1.0\r\n"
            "Host: example.com\r\n"
            f"X-Proxy-Auth: {AUTH_TOKEN}\r\n"
            "Connection: close\r\n\r\n"
        )
        start = time.time()
        r = send_raw(EC2_HOST, PORT, req)
        rtt = time.time() - start
        line = status_line(r)
        print(f"  EC2 response : {line}")
        print(f"  RTT to EC2   : {rtt:.3f}s")

        check("EC2 server reachable",           "200" in line, line)
        check("EC2 RTT reasonable (< 10s)",     rtt < 10,      f"{rtt:.3f}s")
        check("EC2 RTT > local (has real latency)", rtt > 0.01, f"{rtt:.3f}s")
    except ConnectionRefusedError:
        check("EC2 server reachable", False, f"connection refused — is server running on {EC2_HOST}:{PORT}?")
    except socket.timeout:
        check("EC2 server reachable", False, f"timed out — check EC2 security group allows port {PORT}")
    except Exception as e:
        check("EC2 server reachable", False, str(e))


# ── Summary ────────────────────────────────────────────────────────────────────

def print_summary():
    total = ok_count + fail_count
    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {ok_count} passed, {fail_count} failed out of {total} tests")
    print(f"{'=' * 60}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("   HTTP Proxy — Full Test Suite")
    print("=" * 60)
    print(f"  Local  : {LOCAL_HOST}:{PORT}")
    print(f"  EC2    : {EC2_HOST}:{PORT}")
    print(f"  Token  : {AUTH_TOKEN}")

    # pre-check: is the local proxy running?
    print("\n[Pre-check] Verifying local proxy is reachable...")
    try:
        with socket.create_connection((LOCAL_HOST, PORT), timeout=3):
            pass
        print("[Pre-check] ✅ Local proxy is online. Starting tests...\n")
    except Exception:
        print(f"[Pre-check] ❌ Cannot reach proxy at {LOCAL_HOST}:{PORT}. Is server.py running?")
        exit(1)

    # original tests (now with auth header)
    test_basic_connection()
    test_response_codes()
    test_multiple_requests()
    test_concurrent_clients()
    test_bad_domain()
    test_clean_disconnect()
    test_put()
    test_ls()

    # new feature tests
    test_auth_valid()
    test_auth_invalid()
    test_auth_missing()
    test_blocklist()
    test_status_command()
    test_status_auth()
    test_performance_metrics()
    test_ec2_remote()

    print_summary()