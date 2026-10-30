"""Own nftables table only; the rest of the host firewall is never flushed."""
import ipaddress
import re
import os
import uuid
import subprocess
from pathlib import Path


def settings(config):
    item = config['security']['robot']
    if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', item['nft_table']):
        raise ValueError('Invalid nftables table name')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', item['service']):
        raise ValueError('Invalid firewall service name')
    policy = item.get('policy', 'legacy_hub')
    if policy not in ('legacy_hub', 'local_ssh'):
        raise ValueError('Unknown firewall policy')
    source = str(ipaddress.IPv4Address(item['hub_source_ipv4'])) if policy == 'legacy_hub' else None
    ipv6 = [str(ipaddress.IPv6Address(address)) for address in item.get('hub_source_ipv6', [])] if policy == 'legacy_hub' else []
    if not 60 <= item['rollback_seconds'] <= 600:
        raise ValueError('Rollback timeout must be 60–600 seconds')
    return item, source, ipv6


def active_ap_interfaces():
    """Trust NetworkManager's AP role, never an SSID, client IP or subnet."""
    try:
        result = subprocess.run(['nmcli', '-t', '-f', 'UUID,TYPE,DEVICE', 'connection',
                                 'show', '--active'], capture_output=True, text=True, timeout=3)
        if result.returncode:
            return []
        interfaces = []
        for line in result.stdout.splitlines():
            fields = line.split(':')
            if len(fields) != 3:
                continue
            connection, kind, interface = fields
            if kind not in ('wifi', '802-11-wireless') or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}', interface):
                continue
            mode = subprocess.run(['nmcli', '-g', '802-11-wireless.mode', 'connection',
                                   'show', connection], capture_output=True, text=True, timeout=3)
            if mode.returncode == 0 and mode.stdout.strip() == 'ap':
                interfaces.append(interface)
        return sorted(set(interfaces))
    except (OSError, subprocess.TimeoutExpired):
        return []


def recovery_set(interfaces):
    if any(not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}', name) for name in interfaces):
        raise ValueError('Invalid recovery interface')
    return ', '.join('"' + name + '"' for name in interfaces)


def sync_recovery(config):
    item, _, _ = settings(config)
    if item.get('policy') != 'local_ssh':
        return
    table = item['nft_table']
    exists = subprocess.run(['nft', 'list', 'set', 'inet', table, 'recovery_interfaces'],
                            capture_output=True)
    if exists.returncode:
        return
    interfaces = active_ap_interfaces()
    if os.environ.get('REACHY_FIREWALL_ACTION') in ('down', 'pre-down'):
        interfaces = [name for name in interfaces if name != os.environ.get('REACHY_FIREWALL_IFACE')]
    script = f'flush set inet {table} recovery_interfaces\n'
    if interfaces:
        script += f'add element inet {table} recovery_interfaces {{ {recovery_set(interfaces)} }}\n'
    run('nft', '-f', '-', input=script)


def render(config, recovery_interfaces=None):
    item, source, ipv6 = settings(config)
    if item.get('policy') == 'local_ssh':
        interfaces = active_ap_interfaces() if recovery_interfaces is None else recovery_interfaces
        elements = recovery_set(interfaces)
        return '\n'.join([
            f'table inet {item["nft_table"]} {{',
            ' set recovery_interfaces {', '  type ifname;',
            *(['  elements = { ' + elements + ' };'] if elements else []), ' }',
            ' chain input {', '  type filter hook input priority -10; policy drop;',
            '  iifname "lo" accept', '  ct state established,related accept',
            '  ct state invalid drop',
            '  tcp dport 22 accept',
            '  udp sport 67 udp dport 68 accept',
            '  udp sport 547 udp dport 546 accept',
            '  ip protocol icmp accept',
            '  meta l4proto ipv6-icmp accept',
            '  ip daddr 224.0.0.251 udp dport 5353 accept',
            '  ip6 daddr ff02::fb udp dport 5353 accept',
            '  iifname @recovery_interfaces udp sport 68 udp dport 67 accept',
            '  iifname @recovery_interfaces udp dport 53 accept',
            '  iifname @recovery_interfaces tcp dport { 53, 8000, 8443 } accept',
            ' }', '}', ''])
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
Description=Reachy inbound access policy
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


def install_dispatcher(config):
    # Reuse unit() path validation before embedding paths into a shell script.
    unit(config)
    import shlex
    target = Path('/etc/NetworkManager/dispatcher.d/70-reachy-firewall')
    target.write_text('''#!/bin/sh
case "$2" in pre-up|up|pre-down|down|reapply|dhcp4-change|dhcp6-change) ;; *) exit 0 ;; esac
export REACHY_FIREWALL_IFACE="$1" REACHY_FIREWALL_ACTION="$2"
''' + 'export PYTHONPATH=' + shlex.quote(str(config.root / 'src')) + '\n' +
        '/usr/bin/python3 -m reachy_companion --config ' + shlex.quote(str(config.filename)) +
        ' firewall recovery-sync\n')
    target.chmod(0o700)
    for directory in ('pre-up.d', 'pre-down.d'):
        link = target.parent / directory / target.name
        link.parent.mkdir(exist_ok=True)
        if not link.exists():
            link.symlink_to(target)


def main(config, action):
    item, _, _ = settings(config)
    if action == 'render':
        print(render(config), end='')
    elif action == 'apply':
        apply(config)
    elif action == 'recovery-sync':
        sync_recovery(config)
    elif action == 'remove':
        remove(config)
    elif action == 'arm':
        # A unique unit avoids collisions with a previous elapsed timer.
        marker = Path('/run/' + item['service'] + '-rollback-unit')
        if marker.exists():
            previous = marker.read_text().strip()
            if not re.fullmatch(re.escape(item['service']) + r'-rollback-[0-9a-f]{32}', previous):
                raise ValueError('Invalid previous rollback unit')
            active = subprocess.run(['systemctl', 'is-active', '--quiet', previous + '.service'])
            if active.returncode == 0:
                raise RuntimeError('Previous rollback is running; wait before applying rules')
            run('systemctl', 'stop', previous + '.timer')
        name = item['service'] + '-rollback-' + uuid.uuid4().hex
        command = f'systemctl disable --now {item["service"]}.service; nft delete table inet {item["nft_table"]} 2>/dev/null; true'
        run('systemd-run', '--unit=' + name,
            '--on-active=' + str(item['rollback_seconds']) + 's', '/bin/sh', '-c', command)
        marker.write_text(name)
    elif action == 'confirm':
        marker = Path('/run/' + item['service'] + '-rollback-unit')
        name = marker.read_text().strip()
        if not re.fullmatch(re.escape(item['service']) + r'-rollback-[0-9a-f]{32}', name):
            raise ValueError('Invalid rollback unit')
        # An already fired rollback must never be reported as confirmed.
        result = subprocess.run(['systemctl', 'is-active', '--quiet', name + '.timer'])
        if result.returncode:
            raise RuntimeError('Rollback timer is no longer active; reapply and verify')
        run('systemctl', 'stop', name + '.timer')
        marker.unlink()
    elif action == 'install':
        if item.get('policy') == 'local_ssh':
            install_dispatcher(config)
        target = Path('/etc/systemd/system') / (item['service'] + '.service')
        target.write_text(unit(config))
        run('systemctl', 'daemon-reload')
        main(config, 'arm')
        run('systemctl', 'enable', item['service'] + '.service')
        run('systemctl', 'restart', item['service'] + '.service')
        print('Rollback is armed. Verify a NEW SSH connection through hub, then firewall confirm.')
