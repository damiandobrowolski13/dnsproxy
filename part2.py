import socket
import threading
import requests
import dns.message
import dns.rcode

LISTEN_IP = '127.0.0.1'
PROXY_PORT = 1053
HTTPS_DNS_URL = "https://dns.google/resolve"

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
    """
    Use Google's JSON DoH API (/resolve) to answer the first question.
    Convert JSON Answer records into a dns.message response and return wire bytes.
    Supports A and CNAME (and other types that dnspython can parse from text).
    """
    print(f"Received DNS request from {addr}")
    
    try:
        # Parse the incoming UDP DNS request
        dns_query_msg = dns.message.from_wire(data)
        print(f"Parsed DNS message: {dns_query_msg}")
        
        # Extract query details
        question = dns_query_msg.question[0]
        query_name = question.name.to_text()
        query_type = question.rdtype
        
        print(f"Query: {query_name} {query_type}")
        
        # Make HTTPS DNS request using Google's JSON API
        response = None
        for attempt in range(RETRIES):
            try:
                http_response = requests.get(
                    HTTPS_DNS_URL, 
                    params={
                        'name': query_name,
                        'type': query_type
                    },
                    timeout=UPSTREAM_TIMEOUT
                )

                if http_response.status_code == 200:
                    json_response = http_response.json()
                    print(f"JSON response: {json_response}")

                    response = json_to_dns_message(dns_query_msg, json_response)
                    break
                else:
                    raise Exception(f"HTTP {http_response.status_code}: {http_response.text}")
                    
            except Exception as e:
                print(f"HTTPS DNS error (attempt {attempt+1}/{RETRIES}): {e}")
        
        if response is None:
            # Create SERVFAIL response if all attempts failed
            response = dns.message.make_response(dns_query_msg)
            response.set_rcode(dns.rcode.SERVFAIL)
        
        # Send the response back to the original client
        response_bytes = response.to_wire()
        print(f"Response size: {len(response_bytes)} bytes")
        sock.sendto(response_bytes, addr)
        print(f"Sent DNS response back to {addr}")
        
    except Exception as e:
        print(f"Error handling DNS request from {addr}: {e}")
        try:
            error_response = dns.message.make_response(dns.message.from_wire(data))
            error_response.set_rcode(dns.rcode.SERVFAIL)
            sock.sendto(error_response.to_wire(), addr)
        except:
            pass

def json_to_dns_message(original_query, json_response):
    """Transform Google's JSON DNS response back to a UDP DNS message."""
    response = dns.message.make_response(original_query)
    response.set_rcode(json_response.get('Status'))

    if json_response.get('RD'):
        response.flags |= dns.flags.RD
    if json_response.get('RA'):
        response.flags |= dns.flags.RA
    if json_response.get('AD'):
        response.flags |= dns.flags.AD
    if json_response.get('CD'):
        response.flags |= dns.flags.CD
    if json_response.get('TC'):
        response.flags |= dns.flags.TC

    answers = json_response.get('Answer', [])
    for answer in answers:
        name = answer['name']
        rdtype = answer['type']
        ttl = answer['TTL']
        rdata_text = answer['data']

        rdata = dns.rdata.from_text(dns.rdataclass.IN, rdtype, rdata_text)
        response.answer.append(dns.rrset.from_rdata(name, ttl, rdata))
    
    authorities = json_response.get('Authority', [])
    for authority in authorities:
        name = authority['name']
        rdtype = authority['type']
        ttl = authority['TTL']
        rdata_text = authority['data']

        rdata = dns.rdata.from_text(dns.rdataclass.IN, rdtype, rdata_text)
        response.authority.append(dns.rrset.from_rdata(name, ttl, rdata))
    
    return response

if __name__ == "__main__":
    run_proxy()