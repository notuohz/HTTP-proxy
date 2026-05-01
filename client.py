"""
HTTP Proxy Client - Phase 2-ready version
Usage: python client.py <server_machine> <server_port> [AUTH_TOKEN]
Example: python client.py localhost 8888 mySecretToken

Features:
1. Sends X-Proxy-Auth token to server
2. Supports status command for live server monitoring
3. Displays blocklist/security responses from server
4. Shows RTT and throughput after every request
"""

import socket
import sys
import os
import time

BUFFER_SIZE = 4096
DEFAULT_AUTH_TOKEN = "phase2token"


def dns_lookup(hostname: str) -> str:
    # resolve a hostname to an IP address using the system's DNS resolver
    ip = socket.gethostbyname(hostname)
    print(f"[DNS] Resolved '{hostname}' → {ip}")
    return ip


def send_request(proxy_host: str, proxy_port: int, command: str, target: str, auth_token: str, body: str = "") -> tuple:
    # send an HTTP request through the proxy and return (response, rtt, byte_count)
    # command : GET | HEAD | PUT | STATUS
    # target : full URL like http://example.com/path
    # body : optional request body for PUT

    if command == "STATUS":
        raw = (
            "STATUS proxy://status HTTP/1.0\r\n"
            "Host: proxy-status\r\n"
            f"X-Proxy-Auth: {auth_token}\r\n"
            "Connection: close\r\n\r\n"
        )
    elif body:
        raw = (
            f"{command} {target} HTTP/1.0\r\n"
            f"Host: {extract_host(target)}\r\n"
            f"X-Proxy-Auth: {auth_token}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Connection: close\r\n\r\n"
            f"{body}"
        )
    else:
        raw = (
            f"{command} {target} HTTP/1.0\r\n"
            f"Host: {extract_host(target)}\r\n"
            f"X-Proxy-Auth: {auth_token}\r\n"
            f"Connection: close\r\n\r\n"
        )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(10)
        s.connect((proxy_host, proxy_port))

        start_time = time.time()  # start timer just before sending
        s.sendall(raw.encode())

        response = b""
        while True:
            chunk = s.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk

        rtt = time.time() - start_time  # stop timer once full response received

    return response.decode("utf-8", errors="replace"), rtt, len(response)


def print_stats(rtt: float, byte_count: int):
    # print RTT and throughput after every request
    throughput = (byte_count / rtt / 1024) if rtt > 0 else 0
    print(f"\n[Stats] RTT: {rtt:.3f}s | Received: {byte_count} bytes | Throughput: {throughput:.1f} KB/s")


def extract_host(url: str) -> str:
    # pull the hostname out of a URL for the Host header
    url = url.replace("http://", "")
    return url.split("/")[0].split(":")[0]


def split_response(response: str):
    """Split raw HTTP response into headers and body."""
    if "\r\n\r\n" in response:
        return response.split("\r\n\r\n", 1)
    return response, ""


def print_banner(proxy_host: str, proxy_port: int, proxy_ip: str, auth_token: str):
    print("=" * 50)
    print("       HTTP Proxy Client — Phase 2")
    print("=" * 50)
    print(f"  Proxy : {proxy_host} ({proxy_ip})")
    print(f"  Port  : {proxy_port}")
    print(f"  Auth  : token provided ({len(auth_token)} characters)")
    print("=" * 50)
    print()
    print("Commands: get <url>, put <filename> <url>, ls <url>, head <url>, status, quit")
    print()


def main():
    if len(sys.argv) not in (3, 4):
        print("Usage: python client.py <server_machine> <server_port> [AUTH_TOKEN]")
        print("Example: python client.py localhost 8888 mySecretToken")
        sys.exit(1)

    proxy_host = sys.argv[1]
    try:
        proxy_port = int(sys.argv[2])
    except ValueError:
        print("Error: server_port must be an integer.")
        sys.exit(1)

    auth_token = sys.argv[3] if len(sys.argv) == 4 else os.environ.get("PROXY_AUTH_TOKEN", DEFAULT_AUTH_TOKEN)

    try:
        proxy_ip = dns_lookup(proxy_host)
    except socket.gaierror as e:
        print(f"[ERROR] DNS lookup failed for '{proxy_host}': {e}")
        sys.exit(1)

    print_banner(proxy_host, proxy_port, proxy_ip, auth_token)

    # interactive REPL loop
    while True:
        try:
            user_input = input("ftp> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDisconnecting...")
            break

        if not user_input:
            continue

        parts = user_input.split(maxsplit=2)
        cmd = parts[0].lower()

        # quit command
        if cmd == "quit":
            print("Disconnecting from proxy")
            break

        # status command
        elif cmd == "status":
            print("\n[→] STATUS proxy server")
            print("-" * 50)
            try:
                response, rtt, byte_count = send_request(proxy_ip, proxy_port, "STATUS", "proxy://status", auth_token)
                headers, body = split_response(response)
                print(body if body else headers)
                print_stats(rtt, byte_count)
            except socket.timeout:
                print("[ERROR] Request timed out.")
            except ConnectionRefusedError:
                print(f"[ERROR] Could not connect to proxy at {proxy_ip}:{proxy_port}")
            except Exception as e:
                print(f"[ERROR] {e}")
            print("-" * 50 + "\n")

        # get <url> command
        elif cmd == "get":
            if len(parts) < 2:
                print("[ERROR] Usage: get <url>")
                continue

            url = parts[1]
            if not url.startswith("http://"):
                url = "http://" + url

            print(f"\n[→] GET {url}")
            print("-" * 50)
            try:
                response, rtt, byte_count = send_request(proxy_ip, proxy_port, "GET", url, auth_token)
                headers, body = split_response(response)

                print("[Headers]")
                print(headers)
                print("\n[Body preview — first 500 chars]")
                print(body[:500])
                if len(body) > 500:
                    print(f"... [{len(body) - 500} more characters]")

                print_stats(rtt, byte_count)

            except socket.timeout:
                print("[ERROR] Request timed out.")
            except ConnectionRefusedError:
                print(f"[ERROR] Could not connect to proxy at {proxy_ip}:{proxy_port}")
            except Exception as e:
                print(f"[ERROR] {e}")
            print("-" * 50 + "\n")

        # put <filename> <url> command
        elif cmd == "put":
            if len(parts) < 3:
                print("[ERROR] Usage: put <filename> <url>")
                continue

            filename = parts[1]
            url = parts[2]
            if not url.startswith("http://"):
                url = "http://" + url

            if not os.path.exists(filename):
                print(f"[ERROR] File not found: '{filename}'")
                continue

            with open(filename, "r", errors="ignore") as f:
                file_contents = f.read()

            print(f"\n[→] PUT {filename} → {url}")
            print(f"  File size: {len(file_contents)} bytes")
            print("-" * 50)
            try:
                response, rtt, byte_count = send_request(proxy_ip, proxy_port, "PUT", url, auth_token, body=file_contents)
                headers, body = split_response(response)

                print("[Headers]")
                print(headers)
                if body:
                    print("\n[Response body]")
                    print(body[:500])

                print_stats(rtt, byte_count)

            except socket.timeout:
                print("[ERROR] Request timed out.")
            except Exception as e:
                print(f"[ERROR] {e}")
            print("-" * 50 + "\n")

        # ls <url> command
        elif cmd == "ls":
            if len(parts) < 2:
                print("[ERROR] Usage: ls <url>")
                continue

            url = parts[1]
            if not url.startswith("http://"):
                url = "http://" + url

            if not url.endswith("/"):
                url = url + "/"

            print(f"\n[→] LS (GET) {url}")
            print("-" * 50)
            try:
                response, rtt, byte_count = send_request(proxy_ip, proxy_port, "GET", url, auth_token)
                headers, body = split_response(response)

                print("[Headers]")
                print(headers)
                print("\n[Directory listing / Response body]")
                print(body[:500])
                if len(body) > 500:
                    print(f"... [{len(body) - 500} more characters]")

                print_stats(rtt, byte_count)

            except socket.timeout:
                print("[ERROR] Request timed out.")
            except Exception as e:
                print(f"[ERROR] {e}")
            print("-" * 50 + "\n")

        # head <url> command
        elif cmd == "head":
            if len(parts) < 2:
                print("[ERROR] Usage: head <url>")
                continue

            url = parts[1]
            if not url.startswith("http://"):
                url = "http://" + url

            print(f"\n[→] HEAD {url}")
            print("-" * 50)
            try:
                response, rtt, byte_count = send_request(proxy_ip, proxy_port, "HEAD", url, auth_token)
                print(response)
                print_stats(rtt, byte_count)
            except Exception as e:
                print(f"[ERROR] {e}")
            print("-" * 50 + "\n")

        else:
            print(f"[ERROR] Unknown command: '{cmd}'.")


if __name__ == "__main__":
    main()