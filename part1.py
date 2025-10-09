import socket
import threading

PROXY_PORT = 1053
DEFAULT_UPSTREAM_DNS = "8.8.8.8"

def run_proxy():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', PROXY_PORT))
    print(f"DNS proxy listening on port: {PROXY_PORT}")

    while True:
        data, addr = sock.recvfrom(2048)

        # non-blocking request handling
        thread = threading.Thread(target=handle_dns_request, args=(data, addr, sock))
        thread.start()

def handle_dns_request(data, addr, sock):
    print(f"Received DNS request from {addr}")
    print(f"Request data: {data.hex()}")
    
    try:
        upstream_dns_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        upstream_dns_socket.sendto(data, (DEFAULT_UPSTREAM_DNS, 53))
        response, _ = upstream_dns_socket.recvfrom(2048)
        upstream_dns_socket.close()

        sock.sendto(response, addr)
        print(f"Sent response back to {addr}")

    except Exception as e:
        print(f"Error handling DNS request from {addr}: {e}")

if __name__ == "__main__":
    run_proxy()