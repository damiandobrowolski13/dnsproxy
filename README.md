# dnsproxy
A simple DNS proxy with an HTTPS wrapper for DNS over HTTPS (DoH)

## Authors: 
Charles Kozel ()
Damian Dobrowolski (rnz5773)

## How to Run:
1. run the program: `python3 part1.py`
(Press Ctrl-C to stop)

2. query A record for example.com via the proxy on port 1053: `dig @127.0.0.1 -p 1053 example.com A`
(If you want to force upstream failures for testing, change DEFAULT_UPSTREAM_DNS to a non-routable address or reduce UPSTREAM_TIMEOUT in part1.py.)

## Design:
* Main loop: run_proxy() binds a UDP socket on LISTEN_IP:PROXY_PORT and spawns a new thread per incoming packet.
* Per-request handler: handle_dns_request(data, addr, sock)
    * Logs the incoming request and parses the question name/type via parse_dns_request.
    * Opens a short-lived UDP socket to the upstream DNS server, uses UPSTREAM_TIMEOUT and RETRIES to attempt sending the original packet unchanged.
    * If upstream responds, the raw response bytes are forwarded back to the client unmodified (preserving the 2‑byte transaction ID).
    * If all attempts time out, the code crafts and sends a minimal SERVFAIL reply that preserves the original transaction ID and question section (so the client can match the response).
    * The upstream socket is closed in a finally block to avoid leaks.
* DNS parsing: parse_dns_request reads the QNAME and QTYPE from the DNS question (header assumed 12 bytes), maps common type codes to names.
* Configuration: DEFAULT_UPSTREAM_DNS, UPSTREAM_TIMEOUT, RETRIES and ports are top-level constants you can tune.