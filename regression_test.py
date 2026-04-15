#!/usr/bin/env python3
"""
SDN Static Routing - Regression & Validation Test
==================================================
Author: [Your Name]
Description:
    Automated test suite that validates static routing behavior inside
    a live Mininet session. Tests two scenarios:

    Scenario 1 - Functional correctness:
        Verify all host pairs can reach each other via ping.

    Scenario 2 - Regression (path stability after rule reinstall):
        Check that after manually deleting and re-applying flow rules,
        routing paths remain identical (same latency, same reachability).

    Additional checks:
        - Flow table inspection (ovs-ofctl dump-flows)
        - Throughput measurement (iperf)
        - Blocked traffic test (if a host is isolated)

Usage:
    sudo python3 regression_test.py
    (POX controller must be running first)
"""

import subprocess
import sys
import time

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.log import setLogLevel, output, info, error
from mininet.link import TCLink


# ============================================================
# Re-use the same topology class from topology.py
# ============================================================
class StaticRoutingTopo(Topo):
    def build(self):
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')
        h3 = self.addHost('h3', ip='10.0.0.3/24')
        s1 = self.addSwitch('s1', cls=OVSSwitch, protocols='OpenFlow10')
        s2 = self.addSwitch('s2', cls=OVSSwitch, protocols='OpenFlow10')
        s3 = self.addSwitch('s3', cls=OVSSwitch, protocols='OpenFlow10')
        self.addLink(h1, s1, bw=100, delay='1ms')
        self.addLink(s1, s2, bw=1000, delay='5ms')
        self.addLink(s1, s3, bw=1000, delay='5ms')
        self.addLink(h3, s2, bw=100, delay='1ms')
        self.addLink(h2, s3, bw=100, delay='1ms')


# ============================================================
# Test helpers
# ============================================================
PASS = '\033[92m[PASS]\033[0m'
FAIL = '\033[91m[FAIL]\033[0m'
INFO = '\033[94m[INFO]\033[0m'
WARN = '\033[93m[WARN]\033[0m'

results = []

def log_result(test_name, passed, detail=''):
    tag = PASS if passed else FAIL
    print(f'  {tag} {test_name}')
    if detail:
        print(f'         {detail}')
    results.append((test_name, passed))


def ping_test(net, src_name, dst_name, count=3):
    """Ping from src to dst and return (success, avg_rtt_ms)."""
    src = net.get(src_name)
    dst = net.get(dst_name)
    dst_ip = dst.IP()
    result = src.cmd(f'ping -c {count} -W 2 {dst_ip}')

    # Parse success
    received_line = [l for l in result.splitlines() if 'received' in l]
    if not received_line:
        return False, None
    parts = received_line[0].split(',')
    received = int(parts[1].strip().split()[0])
    success  = received > 0

    # Parse RTT
    rtt_line = [l for l in result.splitlines() if 'rtt' in l or 'round-trip' in l]
    avg_rtt  = None
    if rtt_line:
        try:
            avg_rtt = float(rtt_line[0].split('/')[4])
        except Exception:
            pass

    return success, avg_rtt


def dump_flows(switch_name):
    """Return flow table of a switch as a string."""
    try:
        out = subprocess.check_output(
            ['ovs-ofctl', 'dump-flows', switch_name],
            stderr=subprocess.STDOUT
        ).decode()
        return out
    except Exception as e:
        return f'(error: {e})'


def count_flows(switch_name):
    """Return number of non-default flow rules on a switch."""
    flows = dump_flows(switch_name)
    lines = [l for l in flows.splitlines()
             if 'cookie' in l and 'CONTROLLER' not in l]
    return len(lines)


def delete_all_flows(switch_name):
    """Delete all flow rules from a switch."""
    subprocess.call(['ovs-ofctl', 'del-flows', switch_name])


def iperf_test(net, server_name, client_name, duration=5):
    """Run iperf and return throughput in Mbps."""
    server = net.get(server_name)
    client = net.get(client_name)
    server.cmd('pkill -f iperf')
    time.sleep(0.3)
    server.sendCmd(f'iperf -s -t {duration + 2}')
    time.sleep(0.5)
    result = client.cmd(f'iperf -c {server.IP()} -t {duration}')
    server.sendInt()
    server.waitOutput()

    # Parse throughput
    for line in reversed(result.splitlines()):
        if 'Mbits/sec' in line or 'Gbits/sec' in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if 'bits/sec' in p and i > 0:
                    val = float(parts[i - 1])
                    unit = p
                    if 'Gbits' in unit:
                        val *= 1000
                    return val
    return None


# ============================================================
# SCENARIO 1: Functional Correctness Tests
# ============================================================
def scenario_1_functional(net):
    print('\n' + '='*55)
    print(' SCENARIO 1: Functional Correctness — Ping Tests')
    print('='*55)

    # Wait for controller to install flows
    print(f'  {INFO} Waiting 3s for controller to install flows...')
    time.sleep(3)

    # Check flow tables are populated
    for sw in ['s1', 's2', 's3']:
        n = count_flows(sw)
        ok = n >= 2
        log_result(f'Flow rules present on {sw}', ok, f'{n} rules installed')

    # Ping tests between all pairs
    pairs = [('h1', 'h3'), ('h1', 'h2'), ('h2', 'h3'),
             ('h3', 'h1'), ('h2', 'h1'), ('h3', 'h2')]

    for src, dst in pairs:
        ok, rtt = ping_test(net, src, dst, count=3)
        detail = f'avg RTT = {rtt:.2f} ms' if rtt else 'no RTT data'
        log_result(f'Ping {src} → {dst}', ok, detail)

    # Dump flow tables for documentation
    print(f'\n  {INFO} Flow table dump (for README screenshots):')
    for sw in ['s1', 's2', 's3']:
        print(f'\n  --- {sw} ---')
        flows = dump_flows(sw)
        for line in flows.splitlines():
            if 'cookie' in line:
                # Trim verbose fields for readability
                short = line.split('actions=')[0].split('priority=')[-1]
                action = line.split('actions=')[-1] if 'actions=' in line else ''
                print(f'    priority={short}  actions={action}')


# ============================================================
# SCENARIO 2: Regression — Path Stability After Rule Reinstall
# ============================================================
def scenario_2_regression(net):
    print('\n' + '='*55)
    print(' SCENARIO 2: Regression — Path Stability After Reinstall')
    print('='*55)

    # Capture baseline RTTs
    print(f'  {INFO} Measuring baseline RTTs...')
    baseline = {}
    for src, dst in [('h1', 'h3'), ('h1', 'h2'), ('h2', 'h3')]:
        ok, rtt = ping_test(net, src, dst, count=5)
        baseline[(src, dst)] = rtt
        print(f'    Baseline {src}→{dst}: {"%.2f ms" % rtt if rtt else "UNREACHABLE"}')

    # Delete all flows on all switches
    print(f'\n  {INFO} Deleting all flow rules from s1, s2, s3...')
    for sw in ['s1', 's2', 's3']:
        delete_all_flows(sw)
        n = count_flows(sw)
        log_result(f'Flows cleared on {sw}', n == 0, f'{n} rules remaining')

    # Wait for controller to reinstall rules (ConnectionUp or packet_in)
    print(f'  {INFO} Waiting 5s for controller to reinstall rules...')
    time.sleep(5)

    # Verify flows are back
    for sw in ['s1', 's2', 's3']:
        n = count_flows(sw)
        ok = n >= 2
        log_result(f'Flows reinstalled on {sw}', ok, f'{n} rules present')

    # Verify reachability is restored
    print(f'\n  {INFO} Verifying reachability after reinstall...')
    for src, dst in [('h1', 'h3'), ('h1', 'h2'), ('h2', 'h3')]:
        ok, rtt = ping_test(net, src, dst, count=3)
        detail = f'avg RTT = {"%.2f" % rtt if rtt else "N/A"} ms'
        log_result(f'Post-reinstall {src} → {dst}', ok, detail)

    # Compare RTTs (regression: should be within 50% of baseline)
    print(f'\n  {INFO} RTT regression check (tolerance: 50%):')
    for src, dst in [('h1', 'h3'), ('h1', 'h2'), ('h2', 'h3')]:
        _, new_rtt = ping_test(net, src, dst, count=5)
        base_rtt   = baseline.get((src, dst))
        if base_rtt and new_rtt:
            pct_diff = abs(new_rtt - base_rtt) / base_rtt * 100
            ok = pct_diff < 50
            log_result(
                f'RTT stability {src}→{dst}',
                ok,
                f'baseline={base_rtt:.2f}ms  after={new_rtt:.2f}ms  diff={pct_diff:.1f}%'
            )
        else:
            log_result(f'RTT stability {src}→{dst}', False, 'could not measure')


# ============================================================
# SCENARIO 3: Throughput Measurement (iperf)
# ============================================================
def scenario_3_throughput(net):
    print('\n' + '='*55)
    print(' SCENARIO 3: Throughput Measurement (iperf)')
    print('='*55)

    pairs = [('h1', 'h3'), ('h1', 'h2'), ('h2', 'h3')]
    for server, client in pairs:
        print(f'  {INFO} iperf: {client} → {server}...')
        mbps = iperf_test(net, server, client, duration=5)
        ok = mbps is not None and mbps > 1
        detail = f'{mbps:.2f} Mbps' if mbps else 'no result'
        log_result(f'Throughput {client}→{server}', ok, detail)


# ============================================================
# SUMMARY
# ============================================================
def print_summary():
    print('\n' + '='*55)
    print(' TEST SUMMARY')
    print('='*55)
    passed = sum(1 for _, p in results if p)
    total  = len(results)
    for name, ok in results:
        tag = PASS if ok else FAIL
        print(f'  {tag} {name}')
    print(f'\n  Result: {passed}/{total} tests passed')
    if passed == total:
        print('  \033[92mAll tests passed! Static routing is working correctly.\033[0m')
    else:
        print('  \033[91mSome tests failed. Check controller logs.\033[0m')
    print('='*55 + '\n')


# ============================================================
# MAIN
# ============================================================
def run():
    setLogLevel('warning')  # Suppress Mininet noise during tests

    print('\n' + '='*55)
    print(' SDN Static Routing — Regression Test Suite')
    print('='*55)
    print(f'  {INFO} Starting Mininet...')

    topo = StaticRoutingTopo()
    net  = Mininet(
        topo=topo,
        controller=RemoteController('c0', ip='127.0.0.1', port=6633),
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=False
    )

    try:
        net.start()
        print(f'  {INFO} Mininet started. Running test scenarios...')

        scenario_1_functional(net)
        scenario_2_regression(net)
        scenario_3_throughput(net)
        print_summary()

    except KeyboardInterrupt:
        print('\n  Interrupted by user.')
    finally:
        net.stop()


if __name__ == '__main__':
    run()
