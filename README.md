# dnsproxy
A simple DNS proxy w/ an HTTPS wrapper for DNS over HTTPS (DoH)

## Authors: 
Charles Kozel (QHP7002)
Damian Dobrowolski (rnz5773)

## How to Run:
1. run the program: `python3 part1.py`
(Press Ctrl-C to stop)

2. query A record for example.com via the proxy on port 1053: `dig @127.0.0.1 -p 1053 example.com A`
(If you want to force upstream failures for testing, change DEFAULT_UPSTREAM_DNS to a non-routable address or reduce UPSTREAM_TIMEOUT in part1.py.)

## Design:
### Part 1 — UDP proxy
* Main loop: run_proxy() binds a UDP socket on LISTEN_IP:PROXY_PORT & spawns a new thread per incoming packet.
* Per-request handler: handle_dns_request(data, addr, sock)
    * Logs the incoming request & parses the question name/type via parse_dns_request.
    * Opens a short-lived UDP socket to the upstream DNS server, uses UPSTREAM_TIMEOUT & RETRIES to attempt sending the original packet unchanged.
    * If upstream responds, the raw response bytes are forwarded back to the client unmodified (preserving the 2‑byte transaction ID).
    * If all attempts time out, the code crafts & sends a minimal SERVFAIL reply that preserves the original transaction ID & question section (so the client can match the response).
    * The upstream socket is closed in a finally block to avoid leaks.
* DNS parsing: parse_dns_request reads the QNAME & QTYPE from the DNS question (header assumed 12 bytes), maps common type codes to names.
* Configuration: DEFAULT_UPSTREAM_DNS, UPSTREAM_TIMEOUT, RETRIES & ports are top-level constants you can tune.

### Part 2 — DoH Wrapper
Additions for Part 2 implement a simple DNS-over-HTTPS (DoH) wrapper while keeping UDP proxy behavior:

- Purpose: convert incoming DNS-over-UDP queries into HTTPS requests (Google's JSON API) & return valid DNS UDP responses to the client
- Dependencies: requests (HTTP), dnspython (parse/build DNS wire format) [installed w/ pip]
- Request flow:
  1. Receive UDP packet from client & parse the 1st question (QNAME/QTYPE) for logging
  2. Attempt DoH resolution via https://dns.google/resolve using requests (params: name, type)
  3. If the JSON Answer array exists, convert Answer entries to dnspython RRs, build a dns.message response w/ dns.message.make_response(req) to preserve the original ID, flags, & question, then return reply.to_wire() to client
  4. If all resolution attempts fail, craft a minimal SERVFAIL response that preserves the original 2-byte transaction ID & question section so clients can match replies
- Supported types: A & CNAME (others that dnspython can parse from JSON are handled too)