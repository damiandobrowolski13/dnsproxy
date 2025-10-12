from io import BytesIO
import socket
import threading
import struct

LISTEN_IP = '127.0.0.1'
PROXY_PORT = 1053
DEFAULT_UPSTREAM_DNS = "8.8.8.8"
DNS_PORT = 53

# timeout params
UPSTREAM_TIMEOUT = 2.0
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
    print(f"Request data: {parse_dns_request(data)}")
    
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

def parse_dns_request(data):
    reader = BytesIO(data)

    # skip header bytes
    reader.seek(12)

    # parse name
    labels = []
    while True:
        length = reader.read(1)[0]
        if length == 0:
            break
        labels.append(reader.read(length).decode('utf-8'))
    name = ".".join(labels)

    # parse type
    typeInt = struct.unpack("!H", reader.read(2))[0]
    type = DNS_TYPE_MAP.get(typeInt, f"Unknown({typeInt})")

    return name, type

DNS_TYPE_MAP = {
    1: "A",
    2: "NS",
    5: "CNAME",
    6: "SOA",
    12: "PTR",
    13: "HINFO",
    14: "MINFO",
    15: "MX",
    16: "TXT",
    17: "RP",
    18: "AFSDB",
    24: "SIG",
    25: "KEY",
    28: "AAAA",
    29: "LOC",
    33: "SRV",
    35: "NAPTR",
    36: "KX",
    37: "CERT",
    39: "DNAME",
    41: "OPT",
    43: "DS",
    46: "RRSIG",
    47: "NSEC",
    48: "DNSKEY",
    49: "DHCID",
    50: "NSEC3",
    51: "NSEC3PARAM",
    52: "TLSA",
    55: "HIP",
    59: "CDS",
    60: "CDNSKEY",
    61: "OPENPGPKEY",
    62: "CSYNC",
    64: "SVCB",
    65: "HTTPS",
    99: "SPF",
    108: "EUI48",
    109: "EUI64",
    255: "ANY",
    256: "URI",
    257: "CAA",
}

if __name__ == "__main__":
    run_proxy()