#!/bin/bash
sleep 10

# 1. 把 eth0 (小米路由) 设为你现在真实的静态 IP: 172.28.91.100
nmcli connection down "eth0" 2>/dev/null
nmcli connection modify "eth0" ipv4.method manual ipv4.addresses 172.28.91.100/24 ipv4.gateway 172.28.91.1 ipv4.dns "223.5.5.5,114.114.114.114" ipv4.route-metric 100

# 2. 把 eth1 (原路由) 设为备网静态 IP: 192.168.1.150
nmcli connection down "Wired connection 2" 2>/dev/null
nmcli connection modify "Wired connection 2" ipv4.method manual ipv4.addresses 192.168.1.150/24 ipv4.gateway 192.168.1.1 ipv4.dns "223.5.5.5,114.114.114.114" ipv4.route-metric 200

# 3. 重新拉起
nmcli connection up "eth0"
nmcli connection up "Wired connection 2"

# 4. 锁 DNS
chattr -i /etc/resolv.conf 2>/dev/null
echo "nameserver 223.5.5.5" > /etc/resolv.conf
echo "nameserver 114.114.114.114" >> /etc/resolv.conf
chattr +i /etc/resolv.conf 2>/dev/null
