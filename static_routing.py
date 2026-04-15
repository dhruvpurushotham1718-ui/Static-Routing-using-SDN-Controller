"""
SDN Static Routing - POX OpenFlow Controller
=============================================
Author: [Your Name]
Description:
    Implements static routing using pre-defined flow rules installed
    via OpenFlow 1.0 (POX). The controller handles ConnectionUp events
    to detect switch connections and installs bidirectional flow rules
    for all host pairs across all switches.

Topology Reference:
    h1 (10.0.0.1) --- s1 --- s2 --- h3 (10.0.0.3)
                        |
                       s3
                        |
                       h2 (10.0.0.2)

Port Mapping (Mininet autoSetMacs, link order in topology.py):
    s1 (dpid=1): port 1 → h1,  port 2 → s2,  port 3 → s3
    s2 (dpid=2): port 1 → h3,  port 2 → s1
    s3 (dpid=3): port 1 → h2,  port 2 → s1

Run with:
    ./pox.py log.level --DEBUG static_routing
    (place this file as pox/ext/static_routing.py)
"""

from pox.core import core
from pox.lib.util import dpidToStr
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import IPAddr, EthAddr
from pox.lib.packet import ethernet, ipv4, arp
import pox.lib.packet as pkt

log = core.getLogger()

# ==============================================================================
# HOST IP ADDRESSES
# ==============================================================================
H1 = '10.0.0.1'
H2 = '10.0.0.2'
H3 = '10.0.0.3'

# ==============================================================================
# STATIC ROUTING TABLE
# Format: { (dpid, src_ip, dst_ip): out_port }
#
# Port assignments (Mininet, link order in topology.py):
#   s1 (dpid=1): p1=h1,  p2=s2,  p3=s3
#   s2 (dpid=2): p1=h3,  p2=s1
#   s3 (dpid=3): p1=h2,  p2=s1
# ==============================================================================
STATIC_ROUTES = {
    # h1 → h3:  h1 → s1(p2) → s2(p1) → h3
    (1, H1, H3): 2,
    (2, H1, H3): 1,
    # h3 → h1 (reverse)
    (2, H3, H1): 2,
    (1, H3, H1): 1,

    # h1 → h2:  h1 → s1(p3) → s3(p1) → h2
    (1, H1, H2): 3,
    (3, H1, H2): 1,
    # h2 → h1 (reverse)
    (3, H2, H1): 2,
    (1, H2, H1): 1,

    # h2 → h3:  h2 → s3(p2) → s1(p2) → s2(p1) → h3
    (3, H2, H3): 2,
    (1, H2, H3): 2,
    (2, H2, H3): 1,
    # h3 → h2 (reverse)
    (2, H3, H2): 2,
    (1, H3, H2): 3,
    (3, H3, H2): 1,
}

# ARP routing: (dpid, target_ip) -> out_port
ARP_ROUTES = {
    (1, H1): 1,  (1, H2): 3,  (1, H3): 2,
    (2, H1): 2,  (2, H2): 2,  (2, H3): 1,
    (3, H1): 2,  (3, H2): 1,  (3, H3): 2,
}

# Flow rule priorities
PRIORITY_STATIC = 200
PRIORITY_ARP    = 100
PRIORITY_MISS   = 1


# ==============================================================================
# HELPER: send a flow_mod to install a flow rule on a switch
# ==============================================================================
def install_flow(connection, match, out_port, priority=PRIORITY_STATIC,
                 idle_timeout=0, hard_timeout=0):
    """
    Install a flow rule on the switch connected via `connection`.

    Args:
        connection  : POX switch connection object
        match       : ofp_match describing the rule's match fields
        out_port    : output port number for the action
        priority    : rule priority (higher wins on conflict)
        idle_timeout: seconds before rule removed if no traffic (0 = forever)
        hard_timeout: absolute seconds before rule removed (0 = forever)
    """
    msg = of.ofp_flow_mod()
    msg.match       = match
    msg.priority    = priority
    msg.idle_timeout = idle_timeout
    msg.hard_timeout = hard_timeout
    msg.actions.append(of.ofp_action_output(port=out_port))
    connection.send(msg)


# ==============================================================================
# HELPER: send a packet out a specific port (used for ARP packet_in handling)
# ==============================================================================
def send_packet_out(connection, raw_data, out_port, in_port=of.OFPP_NONE):
    """Forward raw packet data out a specific port."""
    msg = of.ofp_packet_out()
    msg.in_port = in_port
    msg.data    = raw_data
    msg.actions.append(of.ofp_action_output(port=out_port))
    connection.send(msg)


# ==============================================================================
# MAIN CONTROLLER COMPONENT
# ==============================================================================
class StaticRoutingController(object):
    """
    POX component that installs static OpenFlow routing rules on every
    switch as soon as it connects to the controller.
    """

    def __init__(self):
        # Listen for switch connection events
        core.openflow.addListeners(self)
        # Map dpid -> connection (for packet_in use)
        self.connections = {}
        log.info('StaticRoutingController ready — waiting for switches...')

    # ------------------------------------------------------------------
    # EVENT: Switch connects
    # ------------------------------------------------------------------
    def _handle_ConnectionUp(self, event):
        """
        Fired when a switch connects. Installs all static routes
        and ARP rules for that switch.
        """
        dpid       = event.dpid
        connection = event.connection
        self.connections[dpid] = connection

        log.info(f'[CONNECT] Switch s{dpid} connected ({dpidToStr(dpid)})')

        # Install static IP routing rules
        self._install_ip_rules(dpid, connection)

        # Install ARP forwarding rules
        self._install_arp_rules(dpid, connection)

        log.info(f'[READY]   Switch s{dpid} fully configured with static routes')

    # ------------------------------------------------------------------
    # EVENT: Switch disconnects
    # ------------------------------------------------------------------
    def _handle_ConnectionDown(self, event):
        dpid = event.dpid
        self.connections.pop(dpid, None)
        log.info(f'[DISCONNECT] Switch s{dpid} disconnected')

    # ------------------------------------------------------------------
    # Install static IP flow rules for a given switch
    # ------------------------------------------------------------------
    def _install_ip_rules(self, dpid, connection):
        """
        Iterate over STATIC_ROUTES and install every rule that belongs
        to this switch (matched by dpid).
        """
        installed = 0
        for (switch_id, src_ip, dst_ip), out_port in STATIC_ROUTES.items():
            if switch_id != dpid:
                continue

            # Match: IPv4 traffic with specific src+dst IP
            match = of.ofp_match()
            match.dl_type  = 0x0800            # Ethernet type: IPv4
            match.nw_src   = IPAddr(src_ip)
            match.nw_dst   = IPAddr(dst_ip)

            install_flow(
                connection,
                match,
                out_port,
                priority=PRIORITY_STATIC,
                idle_timeout=0,   # Static: never expire due to inactivity
                hard_timeout=0    # Static: never expire absolutely
            )

            log.debug(
                f'  [FLOW] s{dpid}: {src_ip} → {dst_ip} out port {out_port}'
            )
            installed += 1

        log.info(f'[IP RULES] s{dpid}: installed {installed} static IP flow rules')

    # ------------------------------------------------------------------
    # Install ARP forwarding rules for a given switch
    # ------------------------------------------------------------------
    def _install_arp_rules(self, dpid, connection):
        """
        Install ARP forwarding rules so ARP requests/replies are directed
        correctly instead of being flooded (which would break static routing).
        """
        installed = 0
        for (switch_id, target_ip), out_port in ARP_ROUTES.items():
            if switch_id != dpid:
                continue

            # Match: ARP packets targeting a specific IP
            match = of.ofp_match()
            match.dl_type  = 0x0806            # Ethernet type: ARP
            match.nw_dst   = IPAddr(target_ip)

            install_flow(
                connection,
                match,
                out_port,
                priority=PRIORITY_ARP,
                idle_timeout=0,
                hard_timeout=0
            )
            installed += 1

        log.info(f'[ARP RULES] s{dpid}: installed {installed} ARP forwarding rules')

    # ------------------------------------------------------------------
    # EVENT: Packet arrives at controller (table-miss)
    # ------------------------------------------------------------------
    def _handle_PacketIn(self, event):
        """
        Handles packets not matched by any flow rule (table-miss).
        Logs the packet details for debugging. In a correctly configured
        static routing setup, this should rarely fire after initial ARP.
        """
        dpid    = event.dpid
        in_port = event.port
        parsed  = event.parsed

        if not parsed:
            return

        eth_pkt = parsed

        # ARP fallback: if ARP reaches controller, forward intelligently
        if eth_pkt.type == ethernet.ARP_TYPE:
            arp_pkt = eth_pkt.payload
            target  = str(arp_pkt.protodst)
            out_port = ARP_ROUTES.get((dpid, target))
            if out_port:
                log.info(
                    f'[PKT_IN/ARP] s{dpid} in_port={in_port} '
                    f'target={target} → forwarding to port {out_port}'
                )
                send_packet_out(event.connection, event.data, out_port, in_port)
            else:
                # Flood as last resort for unknown ARP
                log.warning(
                    f'[PKT_IN/ARP] s{dpid} unknown target {target}, flooding'
                )
                send_packet_out(event.connection, event.data, of.OFPP_FLOOD, in_port)
            return

        # IPv4 fallback: log and drop (should not happen with correct static routes)
        if eth_pkt.type == ethernet.IP_TYPE:
            ip_pkt = eth_pkt.payload
            log.warning(
                f'[PKT_IN/IP] s{dpid} in_port={in_port} '
                f'{ip_pkt.srcip} → {ip_pkt.dstip} — no matching flow rule!'
            )
            return

        log.debug(f'[PKT_IN] s{dpid} in_port={in_port} unhandled ethertype={hex(eth_pkt.type)}')


# ==============================================================================
# POX LAUNCH FUNCTION — required by POX module loader
# ==============================================================================
def launch():
    """
    Entry point called by POX when loading this module.
    Usage: ./pox.py log.level --DEBUG static_routing
    """
    core.registerNew(StaticRoutingController)
    log.info('Static Routing module launched')
