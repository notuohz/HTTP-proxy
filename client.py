"""
HTTP Proxy Client
Usage: python cli.py <server_machine> <server_port>
Example: python cli.py localhost 8888
"""

import socket
import sys
import os

BUFFER_SIZE = 4096



def dns_lookup(hostname: str) -> str:
    # resolve a hostname to an IP address using the system's DNS resolver
    ip = socket.gethostbyname(hostname)
    print(f"[DNS] Resolved '{hostname}' → {ip}")
    return ip


def send_request(proxy_host: str, proxy_port: int, command: str, target: str, body: str = "") -> str:
    # send an HTTP request through the proxy and return the response text
    # command : GET | HEAD | PUT
    # target : full URL like http://example.com/path
    # body : optional request body for PUT

    if body:
        raw = (
            f"{command} {target} HTTP/1.0\r\n"
            f"Host: {extract_host(target)}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Connection: close\r\n\r\n"
            f"{body}"
        )
    else:
        raw = f"{command} {target} HTTP/1.0\r\nHost: {extract_host(target)}\r\nConnection: close\r\n\r\n" # build raw HTTP request string

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s: # create a TCP socket to connect to the proxy
        s.settimeout(10) # set a timeout for the connection
        s.connect((proxy_host, proxy_port)) # connect to the proxy server
        s.sendall(raw.encode())

        response = b""
        while True: # read the full response from the proxy server
            chunk = s.recv(BUFFER_SIZE)
            if not chunk:
                break
            response += chunk

    return response.decode("utf-8", errors="replace") # decode bytes to string, replacing any invalid characters


def extract_host(url: str) -> str:
    # pull the hostname out of a URL for the Host header
    url = url.replace("http://", "") # remove http:// prefix if present, since we only want the host part
    return url.split("/")[0].split(":")[0] # split by / to remove path, then split by : to remove port if present


def print_banner(proxy_host: str, proxy_port: int, proxy_ip: str): # banner to show proxy info when client starts
    print("=" * 50)
    print("       HTTP Proxy Client — Phase 1")
    print("=" * 50)
    print(f"  Proxy : {proxy_host} ({proxy_ip})")
    print(f"  Port  : {proxy_port}")
    print("=" * 50)
    print()


def main():
    # argument handling and setup
    if len(sys.argv) != 3: # check for correct number of command-line arguments
        print("Usage: python client.py <server_machine> <server_port>")
        print("Example: python cli.py localhost 8888")
        sys.exit(1)

    proxy_host = sys.argv[1] # get proxy host from command-line argument
    try:
        proxy_port = int(sys.argv[2]) # get proxy port from command-line argument and convert to integer
    except ValueError:
        print("Error: server_port must be an integer.")
        sys.exit(1)

    # DNS lookup
    try:
        proxy_ip = dns_lookup(proxy_host) # resolve the proxy hostname to an IP address, and handle any DNS lookup errors
    except socket.gaierror as e:
        print(f"[ERROR] DNS lookup failed for '{proxy_host}': {e}")
        sys.exit(1)

    print_banner(proxy_host, proxy_port, proxy_ip)

    # interactive REPL loop to accept user commands
    while True:
        try:
            user_input = input("ftp> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDisconnecting...")
            break

        if not user_input:
            continue

        parts = user_input.split(maxsplit=2) # split user input into command and arguments, allowing for spaces in the argument
        cmd = parts[0].lower()

        # quit command
        if cmd == "quit":
            print("Disconnecting from proxy")
            break

        # get <url> command
        elif cmd == "get":
            if len(parts) < 2:
                print("[ERROR] Usage: get <url>")
                continue

            url = parts[1] # get the URL argument, and ensure it starts with http:// for consistency
            if not url.startswith("http://"):
                url = "http://" + url

            print(f"\n[→] GET {url}") # print the command being sent to the proxy
            print("-" * 50)
            try:
                response = send_request(proxy_ip, proxy_port, "GET", url) # send the GET request through the proxy and get the response

                # split headers from body
                if "\r\n\r\n" in response:
                    headers, body = response.split("\r\n\r\n", 1)
                else:
                    headers, body = response, ""

                print("[Headers]")
                print(headers)
                print("\n[Body preview — first 500 chars]") # only print the first 500 characters of the body to avoid flooding the terminal with large responses
                print(body[:500])
                if len(body) > 500:
                    print(f"... [{len(body) - 500} more characters]")

            except socket.timeout:
                print("[ERROR] Request timed out.") # handle a timeout error
            except ConnectionRefusedError:
                print(f"[ERROR] Could not connect to proxy at {proxy_ip}:{proxy_port}") # handle connection refused error when trying to connect to the proxy
            except Exception as e:
                print(f"[ERROR] {e}")
            print("-" * 50 + "\n")

        # put <filename> <url> command
        elif cmd == "put":
            if len(parts) < 3:
                print("[ERROR] Usage: put <filename> <url>")
                continue

            filename = parts[1] # get the filename argument
            url = parts[2] # get the URL argument
            if not url.startswith("http://"):
                url = "http://" + url

            if not os.path.exists(filename): # check if the file exists before trying to read it
                print(f"[ERROR] File not found: '{filename}'")
                continue

            with open(filename, "r", errors="ignore") as f: # read the file contents to send as the request body
                file_contents = f.read()

            print(f"\n[→] PUT {filename} → {url}")
            print(f"  File size: {len(file_contents)} bytes")
            print("-" * 50)
            try:
                response = send_request(proxy_ip, proxy_port, "PUT", url, body=file_contents) # send the PUT request with file contents as body

                # split headers from body
                if "\r\n\r\n" in response:
                    headers, body = response.split("\r\n\r\n", 1)
                else:
                    headers, body = response, ""

                print("[Headers]")
                print(headers)
                if body:
                    print("\n[Response body]")
                    print(body[:500])

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

            if not url.endswith("/"): # ensure URL ends with / to request a directory listing
                url = url + "/"

            print(f"\n[→] LS (GET) {url}")
            print("-" * 50)
            try:
                response = send_request(proxy_ip, proxy_port, "GET", url) # ls sends a GET request to the URL, treating the response as a directory listing

                # split headers from body
                if "\r\n\r\n" in response:
                    headers, body = response.split("\r\n\r\n", 1)
                else:
                    headers, body = response, ""

                print("[Headers]")
                print(headers)
                print("\n[Directory listing / Response body]")
                print(body[:500])
                if len(body) > 500:
                    print(f"... [{len(body) - 500} more characters]")

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
                response = send_request(proxy_ip, proxy_port, "HEAD", url)
                print(response)
            except Exception as e:
                print(f"[ERROR] {e}")
            print("-" * 50 + "\n")

        else:
            print(f"[ERROR] Unknown command: '{cmd}'.")


if __name__ == "__main__":
    main()