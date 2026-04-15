# SDN Static Routing using POX Controller

## Problem Statement

This project implements **static routing** in a Software-Defined Network using the **POX OpenFlow controller** and **Mininet**. Instead of dynamic route learning, the controller pre-installs explicit flow rules on each switch so that packets between any two hosts always follow a deterministic, pre-defined path.

**Key objectives:**
- Design a multi-switch topology with defined routing paths
- Install static flow rules via OpenFlow (match on src/dst IP → action output port)
- Validate packet delivery with ping and iperf
- Document routing behavior and flow tables
- Regression test: confirm routing paths are identical after flow rule reinstall

---

## Topology

```
h1 (10.0.0.1) --- s1 --- s2 --- h3 (10.0.0.3)
                   |
                  s3
                   |
                  h2 (10.0.0.2)
```

| Switch | Port 1 | Port 2 | Port 3 |
|--------|--------|--------|--------|
| s1     | h1     | s2     | s3     |
| s2     | h3     | s1     | —      |
| s3     | h2     | s1     | —      |

**Static Paths:**

| Source | Destination | Path              |
|--------|-------------|-------------------|
| h1     | h3          | h1 → s1 → s2 → h3 |
| h1     | h2          | h1 → s1 → s3 → h2 |
| h2     | h3          | h2 → s3 → s1 → s2 → h3 |
| (all paths are bidirectional) | | |

---

## Files

| File | Description |
|------|-------------|
| `static_routing.py` | POX controller — installs static flow rules on switch connect |
| `topology.py` | Mininet topology with 3 switches and 3 hosts |
| `regression_test.py` | Automated test suite (2 scenarios + throughput) |
| `run.sh` | One-command launcher for controller + Mininet |

---

## Setup & Execution

### Prerequisites

```bash
# Install Mininet
sudo apt-get install mininet

# Install POX (clone into home directory)
git clone https://github.com/noxrepo/pox.git ~/pox

# Install Open vSwitch (usually bundled with Mininet)
sudo apt-get install openvswitch-switch
```

### Step 1 — Copy controller to POX extensions folder

```bash
cp static_routing.py ~/pox/ext/
```

### Step 2 — Start the POX Controller (Terminal 1)

```bash
cd ~/pox
./pox.py log.level --DEBUG static_routing
```

Expected output:
```
POX 0.x ... / ...
INFO:static_routing:Static Routing module launched
INFO:static_routing:StaticRoutingController ready — waiting for switches...
```

### Step 3 — Start Mininet Topology (Terminal 2)

```bash
sudo python3 topology.py
```

Expected output:
```
=======================================================
 SDN Static Routing -- Mininet Ready
=======================================================
 Hosts:    h1=10.0.0.1   h2=10.0.0.2   h3=10.0.0.3
...
mininet>
```

### Step 4 — Run Regression Tests (Optional, Terminal 2 or 3)

```bash
# Stop Mininet first if running, then:
sudo python3 regression_test.py
```

---

## Manual Test Commands (inside Mininet CLI)

```bash
# Connectivity tests
mininet> h1 ping -c 3 h3
mininet> h1 ping -c 3 h2
mininet> h2 ping -c 3 h3
mininet> pingall

# Throughput test (iperf)
mininet> h3 iperf -s &
mininet> h1 iperf -c 10.0.0.3 -t 5

# Inspect flow tables
mininet> sh ovs-ofctl dump-flows s1
mininet> sh ovs-ofctl dump-flows s2
mininet> sh ovs-ofctl dump-flows s3

# View switch ports
mininet> sh ovs-ofctl show s1
```

---

## Expected Output

### Ping (h1 → h3)
```
PING 10.0.0.3 (10.0.0.3) 56(84) bytes of data.
64 bytes from 10.0.0.3: icmp_seq=1 ttl=64 time=12.3 ms
64 bytes from 10.0.0.3: icmp_seq=2 ttl=64 time=11.8 ms
64 bytes from 10.0.0.3: icmp_seq=3 ttl=64 time=12.1 ms
--- 10.0.0.3 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss
rtt min/avg/max = 11.8/12.0/12.3 ms
```

### Flow Table (s1)
```
cookie=0x0, duration=..., table=0, n_packets=..., priority=200,
  ip,nw_src=10.0.0.1,nw_dst=10.0.0.3  actions=output:2
cookie=0x0, duration=..., priority=200,
  ip,nw_src=10.0.0.3,nw_dst=10.0.0.1  actions=output:1
...
```

### iperf Result
```
[  3]  0.0- 5.0 sec   55.2 MBytes   92.8 Mbits/sec
```

### Regression Test Output
```
=======================================================
 SDN Static Routing — Regression Test Suite
=======================================================
  SCENARIO 1: Functional Correctness — Ping Tests
  [PASS] Flow rules present on s1  (6 rules installed)
  [PASS] Flow rules present on s2  (4 rules installed)
  [PASS] Flow rules present on s3  (4 rules installed)
  [PASS] Ping h1 → h3  avg RTT = 12.3 ms
  [PASS] Ping h1 → h2  avg RTT = 12.1 ms
  [PASS] Ping h2 → h3  avg RTT = 13.5 ms

  SCENARIO 2: Regression — Path Stability After Reinstall
  [PASS] Flows cleared on s1
  [PASS] Flows reinstalled on s1
  [PASS] RTT stability h1→h3  baseline=12.3ms  after=12.5ms  diff=1.6%

  Result: 18/18 tests passed
```

---

## SDN Concepts Used

| Concept | Implementation |
|---------|---------------|
| **Packet_in** | Controller handles initial packets; installs rules on `ConnectionUp` |
| **Match fields** | `dl_type=0x0800` (IPv4), `nw_src`, `nw_dst` |
| **Actions** | `output:<port>` — deterministic forwarding |
| **Flow priority** | Static routes: 200, ARP: 100, Table-miss: 1 |
| **Idle/Hard timeout** | 0 (rules never expire — truly static) |
| **Flow table** | Inspected with `ovs-ofctl dump-flows` |

---
## Screenshots:

## Topology Setup
<img width="975" height="431" alt="image" src="https://github.com/user-attachments/assets/666dd358-60d6-45b8-93b8-74f8bdc18f32" />

## Starting Controller
<img width="975" height="262" alt="image" src="https://github.com/user-attachments/assets/3f59ae77-b532-4f63-bbce-2711aaf278f3" />

## Run Topology
<img width="975" height="485" alt="image" src="https://github.com/user-attachments/assets/4675e57d-66a3-4ce7-89c2-6e20f56f1d1a" />

## Test Connectivity
<img width="975" height="444" alt="image" src="https://github.com/user-attachments/assets/48ba5e75-35e1-4129-ab0c-c195c110ad29" />
<img width="975" height="1097" alt="image" src="https://github.com/user-attachments/assets/4b23b934-37a1-4ec2-a109-4937bf282640" />

## Path Verification
<img width="975" height="641" alt="image" src="https://github.com/user-attachments/assets/67b5480c-6fd1-4c47-ba6b-c5e239005ff1" />

## Regression test
<img width="975" height="122" alt="image" src="https://github.com/user-attachments/assets/84bc6113-10fb-4764-a697-e54d2ef0566f" />


## References

1. Mininet documentation: http://mininet.org/
2. POX Wiki: https://noxrepo.github.io/pox-doc/html/
3. OpenFlow 1.0 specification: https://opennetworking.org/wp-content/uploads/2013/04/openflow-spec-v1.0.0.pdf
4. Open vSwitch manual: https://www.openvswitch.org/
5. Lantz, B., Heller, B., McKeown, N. (2010). *A Network in a Laptop: Rapid Prototyping for Software-Defined Networks*. HotNets-IX.
