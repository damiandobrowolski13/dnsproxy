from io import BytesIO
import socket
import threading
import struct
import dns.message
import dns.rdata
import dns.rdatatype
import dns.rdataclass
import dns.rrset
import requests

LISTEN_IP = '127.0.0.1'
PROXY_PORT = 1053
DEFAULT_UPSTREAM_DNS = "8.8.8.8"
DNS_PORT = 53

# timeout params
UPSTREAM_TIMEOUT = 2.0
RETRIES = 3             

# DoH configuration
DOH_ENABLED = True
DOH_JSON_ENDPOINT = "https://dns.google/resolve"

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
    # init locals to avoid UnboundLocalError
    response = None
    upstream_dns_socket = None

    # try DoH JSON first for supported types
    if DOH_ENABLED:
        try:
            doh_resp = doh_resolve_via_json(data)
            if doh_resp:
                response = doh_resp
                print("Resolved via DoH (JSON)")
        except Exception as e:
            print(f"DoH attempt failed: {e}")

    # fallback to UDP upstream
    if response is None:
        try:
            upstream_dns_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            upstream_dns_socket.settimeout(UPSTREAM_TIMEOUT)

            for attempt in range(RETRIES):
                try:
                    upstream_dns_socket.sendto(data, (DEFAULT_UPSTREAM_DNS, DNS_PORT))
                    response, _ = upstream_dns_socket.recvfrom(2048)
                    break
                except socket.timeout:
                    print(f"Upstream timeout (attempt {attempt+1}/{RETRIES})")
                except Exception as e:
                    print(f"Upstream error on attempt {attempt+1}/{RETRIES}: {e}")
        except Exception as e:
            print(f"Error contacting upstream UDP server: {e}")

    # if still no response, minimal SERVFAIL to preserve ID & questions
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

    print(f"Response size: {len(response)} bytes")
    try:
        sock.sendto(response, addr)
    except Exception as e:
        print(f"Failed to send response to {addr}: {e}")

    finally:
        if upstream_dns_socket:
            upstream_dns_socket.close()

def doh_resolve_via_json(request_wire):
    """
    Use Google's JSON DoH API (/resolve) to answer the first question.
    Convert JSON Answer records into a dns.message response and return wire bytes.
    Supports A and CNAME (and other types that dnspython can parse from text).
    Returns bytes on success, or None if no answer could be produced.
    """
    try:
        req = dns.message.from_wire(request_wire)
    except Exception:
        return None
    
    if not req.question:
        return None
    
    q = req.question[0]
    # use dnspython name API
    qname_text = q.name.to_text().rstrip('.')
    qtype_int = q.rdtype

    params = {'name': qname_text, 'type': qtype_int}
    try:
        r = requests.get(DOH_JSON_ENDPOINT, params=params, timeout=UPSTREAM_TIMEOUT)
        if r.status_code != 200:
            return None
        j = r.json()
    except Exception:
        return None
    
    if 'Answer' not in j:
        return None
    
    # build response prevering original request (ID, flags, question)
    reply = dns.message.make_response(req)

    for ans in j.get('Answer', []):
        try:
            atype = int(ans.get('type'))
            ttl = int (ans.get('TTL') or ans.get('ttl') or 0)
            data_text = ans.get('data')
            # create rdata & rrset
            rdata_obj = dns.rdata.from_text(dns.rdataclass.IN, atype, data_text)
            rrset = dns.rrset.RRset(q.name, dns.rdataclass.IN, atype)
            rrset.add(rdata_obj, ttl)
            reply.answer.append(rrset)
        except Exception:
            # skip records we cannot parse/convert
            continue

    # if didn't add any answers, return None so caller falls back
    if not reply.answer:
        return None

    return reply.to_wire()

def parse_dns_request(data):
    """
    Parse QNAME and QTYPE for logging. Returns (qname, qtype_str).
    Non-fatal: returns placeholders on parse failure.
    """
    try:
        # attempt to use dnspython for robust parsing
        try:
            msg = dns.message.from_wire(data)
            if msg.question:
                q = msg.question[0]
                return q.name.to_text().rstrip('.'), dns.rdatatype.to_text(q.rdtype)
        except Exception:
            pass

        # fallback to simple manual parse
        reader = BytesIO(data)

        # skip header bytes
        reader.seek(12)

        # parse name
        labels = []
        while True:
            b = reader.read(1)
            if not b:
                break
            length = b[0]
            if length == 0:
                break
            labels.append(reader.read(length).decode('utf-8', errors='replace'))
        name = ".".join(labels)
        tbytes = reader.read(2)
        if len(tbytes) < 2:
            return name or "<parse_error>", "UNKNOWN"
        typeInt = struct.unpack("!H", tbytes)[0]
        return name or "<parse_error>", DNS_TYPE_MAP.get(typeInt, f"Unknown({typeInt})")
    except Exception:
        return "<parse_error>", "UNKNOWN"

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