#!/bin/sh

# Need these loaded for tftp server to work
echo "Ensuring tftp kernel modules are loaded..."
modprobe nf_conntrack_tftp
modprobe nf_nat_tftp
modprobe nf_conntrack_ftp
modprobe nf_conntrack_netbios_ns

# Add some rules to track tftp traffic
WLAN_IF=eth0
iptables -A INPUT -i $WLAN_IF -p udp -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i $WLAN_IF -p udp --dport 69 -m state --state NEW -j ACCEPT


echo "Rebuilding docker compose..."
python ../build_tools/rebuild_compose.py

if [ $1 == "b" ]; then
  echo "Building docker containers..."
  docker-compose build
fi

echo "Bringing up containers..."
docker-compose up -d


echo "Bringing up bridge for fog..."
#ope-fog/pipework br-ope ope-fog 192.168.10.27/24
#brctl addif br10 eth0
#ip addr add 192.168.10.27/24 dev br10
