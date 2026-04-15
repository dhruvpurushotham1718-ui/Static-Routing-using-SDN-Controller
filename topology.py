#!/usr/bin/env python3
"""
SDN Static Routing - Mininet Topology
======================================
Topology:
    h1 (10.0.0.1) --- s1 --- s2 --- h3 (10.0.0.3)
                        |
                       s3
                        |
                       h2 (10.0.0.2)

Switch port mapping (matches STATIC_ROUTES in static_routing.py):
    s1: port 1 → h1,  port 2 → s2,  port 3 → s3
    s2: port 1 → h3,  port 2 → s1
    s3: port 1 → h2,  port 2 → s1

Run:
    sudo python3 topology.py
    (Start the POX controller first!)
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink


class StaticRoutingTopo(Topo):
    """
    Three-switch topology for static routing demonstration.
    Link order matters — it determines port numbers on each switch.
    """

    def build(self):
        # ---- Hosts ----
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')
        h3 = self.addHost('h3', ip='10.0.0.3/24')

        # ---- Switches (OpenFlow 1.0 for POX compatibility) ----
        s1 = self.addSwitch('s1', cls=OVSSwitch, protocols='OpenFlow10')
        s2 = self.addSwitch('s2', cls=OVSSwitch, protocols='OpenFlow10')
        s3 = self.addSwitch('s3', cls=OVSSwitch, protocols='OpenFlow10')

        # ---- Links (order determines port numbers!) ----
        # s1 ports: 1=h1, 2=s2, 3=s3
        self.addLink(h1, s1, bw=100, delay='1ms')   # s1-eth1 <-> h1-eth0
        self.addLink(s1, s2, bw=1000, delay='5ms')  # s1-eth2 <-> s2-eth2
        self.addLink(s1, s3, bw=1000, delay='5ms')  # s1-eth3 <-> s3-eth2

        # s2 ports: 1=h3, 2=s1
        self.addLink(h3, s2, bw=100, delay='1ms')   # s2-eth1 <-> h3-eth0

        # s3 ports: 1=h2, 2=s1
        self.addLink(h2, s3, bw=100, delay='1ms')   # s3-eth1 <-> h2-eth0


def run():
    """Launch Mininet with a remote POX controller."""
    setLogLevel('info')

    topo = StaticRoutingTopo()
    net  = Mininet(
        topo=topo,
        controller=RemoteController('c0', ip='127.0.0.1', port=6633),
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=False
    )

    net.start()

    info('\n')
    info('=======================================================\n')
    info(' SDN Static Routing -- Mininet Ready\n')
    info('=======================================================\n')
    info(' Hosts:    h1=10.0.0.1   h2=10.0.0.2   h3=10.0.0.3\n')
    info(' Switches: s1 (hub), s2 (->h3), s3 (->h2)\n')
    info('-------------------------------------------------------\n')
    info(' Defined static paths:\n')
    info('   h1 <-> h3 : h1-s1-s2-h3\n')
    info('   h1 <-> h2 : h1-s1-s3-h2\n')
    info('   h2 <-> h3 : h2-s3-s1-s2-h3\n')
    info('-------------------------------------------------------\n')
    info(' Quick tests:\n')
    info('   mininet> h1 ping -c 3 h3\n')
    info('   mininet> h1 ping -c 3 h2\n')
    info('   mininet> h2 ping -c 3 h3\n')
    info('   mininet> pingall\n')
    info('   mininet> h3 iperf -s &\n')
    info('   mininet> h1 iperf -c 10.0.0.3 -t 5\n')
    info('=======================================================\n\n')

    CLI(net)
    net.stop()

from mininet.topo import Topo

class MyTopo(Topo):
    def build(self):
        # Add hosts
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')

        # Add switches
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')

        # Add links
        self.addLink(h1, s1)
        self.addLink(s1, s2)
        self.addLink(s2, h2)


topos = {
    'mytopo': (lambda: MyTopo())
}

if __name__ == '__main__':
    run()
