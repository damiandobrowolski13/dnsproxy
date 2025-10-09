import socket
import threading

LISTEN_IP = '127.0.0.1'
PROXY_PORT = 1053
DEFAULT_UPSTREAM_DNS = "8.8.8.8"
DNS_PORT = 53

# timeout params
UPSTREAM_TIMEOUT = 0.0000000002
RETRIES = 3                

def run_proxy():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IP, PROXY_PORT))
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
        upstream_dns_socket.settimeout(UPSTREAM_TIMEOUT)
        response = None

        for attempt in range(RETRIES):
            try:
                upstream_dns_socket.sendto(data, (DEFAULT_UPSTREAM_DNS, DNS_PORT))
                response, _ = upstream_dns_socket.recvfrom(2048)
                break
            except socket.timeout:
                print(f"Upstream timeout (attempt {attempt+1}/{RETRIES})")
            except Exception as e:
                print(f"Upstream error on attempt {attempt+1}/{RETRIES}: {e}")
                response = 'ERROR: Upstream DNS unreachable'.encode()

        if response is None:
            try:
                # preserve original 2-byte ID and question section
                id_bytes = data[0:2]
                qdcount = data[4:6]
                # flags: QR=1, RCODE=2 (SERVFAIL) -> 0x8182; set answer/authority/additional counts to 0
                servfail_hdr = id_bytes + b'\x81\x82' + qdcount + b'\x00\x00\x00\x00\x00\x00'
                question = data[12:]
                response = servfail_hdr + question
                print("No upstream reply — sending SERVFAIL to client")
            except Exception:
                response = b''

        sock.sendto(response, addr)
        print(f"Sent response back to {addr}")
    
    except Exception as e:
        print(f"Error handling DNS request in thread from {addr}: {e}")
    finally:
        if upstream_dns_socket:
            upstream_dns_socket.close()

if __name__ == "__main__":
    run_proxy()