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
        response = None

        attempt = 0
        while attempt < 3:
            try:
                upstream_dns_socket.sendto(data, (DEFAULT_UPSTREAM_DNS, 53))
                response, _ = upstream_dns_socket.recvfrom(2048)
                break
            
            except Exception as e:
                attempt += 1
                if attempt == 3:
                    print(f"Failed to get response from upstream DNS after 3 attempts: {e}")
                    response = 'ERROR: Upstream DNS unreachable'.encode()

        sock.sendto(response, addr)
        print(f"Sent response back to {addr}")
        upstream_dns_socket.close()

    except Exception as e:
        print(f"Error handling DNS request in thread from {addr}: {e}")

 

if __name__ == "__main__":
    run_proxy()