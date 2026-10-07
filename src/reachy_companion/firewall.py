"""Own nftables table only; the rest of the host firewall is never flushed."""
import ipaddress
import re
import subprocess
from pathlib import Path


def settings(config):
    item = config['security']['robot']
    if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', item['nft_table']):
        raise ValueError('Invalid nftables table name')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', item['service']):
        raise ValueError('Invalid firewall service name')
    source = str(ipaddress.IPv4Address(item['hub_source_ipv4']))
    ipv6 = [str(ipaddress.IPv6Address(address)) for address in item['hub_source_ipv6']]
    if not 60 <= item['rollback_seconds'] <= 600:
        raise ValueError('Rollback timeout must be 60–600 seconds')
    return item, source, ipv6


def render(config):
    item, source, ipv6 = settings(config)
    rules = [f'table inet {item["nft_table"]} {{',
             ' chain input {', '  type filter hook input priority -10; policy drop;',
             '  iifname "lo" accept', '  ct state established,related accept',
             f'  ip saddr {source} accept']
    rules += [f'  ip6 saddr {address} accept' for address in ipv6]
    if item['allow_dhcp']:
        rules += ['  udp sport 67 udp dport 68 accept', '  udp sport 547 udp dport 546 accept']
    # IPv6 link operation remains possible, but no TCP/UDP application access.
    rules += ['  meta l4proto ipv6-icmp icmpv6 type { nd-router-advert, nd-neighbor-solicit, nd-neighbor-advert, packet-too-big, destination-unreachable, time-exceeded, parameter-problem } accept',
              ' }', '}', '']
    return '\n'.join(rules)


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def apply(config):
    item, _, _ = settings(config)
    previous = subprocess.run(['nft', 'list', 'table', 'inet', item['nft_table']], capture_output=True)
    script = (f'delete table inet {item["nft_table"]}\n' if previous.returncode == 0 else '') + render(config)
    run('nft', '--check', '-f', '-', input=script)
    run('nft', '-f', '-', input=script)


def remove(config):
    item, _, _ = settings(config)
    subprocess.run(['nft', 'delete', 'table', 'inet', item['nft_table']], check=False)


def unit(config):
    item, _, _ = settings(config)
    # Paths become arguments in systemd syntax; disallow whitespace/control characters.
    paths = (str(config.root / 'src'), str(config.filename))
    if any(any(c.isspace() or c in '%"\\' for c in value) for value in paths):
        raise ValueError('Firewall installation path must have no whitespace or systemd escapes')
    return f'''[Unit]
Description=Reachy inbound access from hub only
DefaultDependencies=no
Wants=network-pre.target
After=local-fs.target
Before=network-pre.target shutdown.target reachy-voice-agent.service
Conflicts=shutdown.target
[Service]
Type=oneshot
RemainAfterExit=yes
Environment=PYTHONPATH={paths[0]}
ExecStart=/usr/bin/python3 -m reachy_companion --config {paths[1]} firewall apply
ExecStop=/usr/bin/python3 -m reachy_companion --config {paths[1]} firewall remove
[Install]
WantedBy=multi-user.target
'''


def main(config, action):
    item, _, _ = settings(config)
    if action == 'render':
        print(render(config), end='')
    elif action == 'apply':
        apply(config)
    elif action == 'remove':
        remove(config)
    elif action == 'arm':
        # Rollback disables persistence as well as removing the active table.
        command = f'systemctl disable --now {item["service"]}.service; nft delete table inet {item["nft_table"]}'
        run('systemd-run', '--unit=' + item['service'] + '-rollback',
            '--on-active=' + str(item['rollback_seconds']) + 's', '/bin/sh', '-c', command)
    elif action == 'confirm':
        run('systemctl', 'stop', item['service'] + '-rollback.timer')
    elif action == 'install':
        target = Path('/etc/systemd/system') / (item['service'] + '.service')
        target.write_text(unit(config))
        run('systemctl', 'daemon-reload')
        main(config, 'arm')
        run('systemctl', 'enable', item['service'] + '.service')
        run('systemctl', 'restart', item['service'] + '.service')
        print('Rollback is armed. Verify a NEW SSH connection through hub, then firewall confirm.')
