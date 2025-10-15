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

### Part 3 - Long Lived HTTPS Sessions
Mostly the same code as part2.py, except instead of making a new TCP/TLS connection for each DNS request to google a long lived requests.Session() is used. This reduces the latency by leaving the TCP/TLS connection open across multiple DNS queries, reducing the initial handshake time to setup the TCP/TLS connection. 

#### Performance Results
Run #1
```
Sent DNS response back to ('127.0.0.1', 50699). Elapsed time: 75.26ms
Sent DNS response back to ('127.0.0.1', 61181). Elapsed time: 26.87ms
Sent DNS response back to ('127.0.0.1', 54444). Elapsed time: 25.29ms
Sent DNS response back to ('127.0.0.1', 51654). Elapsed time: 27.45ms
Sent DNS response back to ('127.0.0.1', 56252). Elapsed time: 23.09ms
```

Run #2
```
Sent DNS response back to ('127.0.0.1', 54593). Elapsed time: 66.05ms
Sent DNS response back to ('127.0.0.1', 58327). Elapsed time: 17.77ms
Sent DNS response back to ('127.0.0.1', 49450). Elapsed time: 11.41ms
Sent DNS response back to ('127.0.0.1', 61601). Elapsed time: 36.45ms
Sent DNS response back to ('127.0.0.1', 54300). Elapsed time: 34.52ms
```

Run #3
```
Sent DNS response back to ('127.0.0.1', 55567). Elapsed time: 93.91ms
Sent DNS response back to ('127.0.0.1', 50372). Elapsed time: 12.85ms
Sent DNS response back to ('127.0.0.1', 53019). Elapsed time: 10.70ms
Sent DNS response back to ('127.0.0.1', 56118). Elapsed time: 25.43ms
Sent DNS response back to ('127.0.0.1', 56017). Elapsed time: 33.79ms
```

#### Analysis
Based on the results above, the first request takes the most time compared to later requests which is expected. 

The performance benefit for later requests is at least 2x faster, and up to 7x faster as seen in Run #3 between requests 1 and 2. 