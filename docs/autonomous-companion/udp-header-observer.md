# Finite kernel header observer

This diagnostic helper does not alter the lease protocol, route, firewall, interface configuration or Wi-Fi settings. It requires Linux and CAP_NET_RAW/root. The receiving AF_PACKET socket starts with protocol zero. The helper attaches exact-flow cBPF, locks it with SO_LOCK_FILTER, confirms replacement is denied, enables kernel timestamps, then binds reception. Kernel acceptance returns exactly42 bytes; rejection returns0. Fixed42-byte recvmsg buffers with MSG_TRUNC verify that the kernel delivered42 bytes without truncation flags. There is no full-packet or userspace-redaction fallback. Linux documents [filter attachment and locking](https://docs.kernel.org/networking/filter.html).

The filter admits only the selected two IPv4 addresses and server UDP port in the correct direction. Client ephemeral port is recorded for later matching to the owned probe. It rejects foreign flow, wrong-direction ports, IPv6, VLAN, IPv4 options, all fragments including MF/offset, reserved fragment flags, short/inconsistent IP/UDP lengths and zero ports. No payload, MAC address, checksum, token or nonce is printed or saved.

First stage exact committed source and run the synthetic kernel preflight on each host (loopback synthetic frames only):

```text
PYTHONPATH=<stage>/src <existing-python> <stage>/deploy/autonomous/udp_header_observer.py --self-test --output <fresh-private-preflight.json>
```

Require all positive/reject vector checks, kernel_snaplen42, filter_lockedtrue and drops0. Any missing capability, filter lock, timestamp, link layout, truncation proof or preflight failure stops the experiment; do not install tools or use a weaker fallback. The local isolated Linux container preflight passed17vectors with4accepted loopback packet copies and0drops; host preflights remain necessary.

For the reviewed finite run, start one observer per host before the first hello, specifying its local Ethernet-layout interface and the same endpoint pair/server port:

```text
PYTHONPATH=<stage>/src <existing-python> <stage>/deploy/autonomous/udp_header_observer.py --interface <local-interface> --client-ip <Hub-IPv4> --server-ip <Reachy-IPv4> --server-port 8781 --duration 20 --max-records 2000 --output <fresh-private-metadata.json>
```

Managed execution must also have a finite runtime limit. Maximum duration25seconds and2000records are enforced internally; outputs use exclusive creation/mode0600. Receipts contain direction, client port, IPID, IP/UDP lengths, kernel local wall timestamp, local userspace monotonic receipt timestamp and local delivery delay. The kernel packet/drop statistics are read once at completion. A drop, cap, clock anomaly or unsupported capture layout makes absence evidence inconclusive. Excluded layouts are not counted by this filter. The metadata alone never declares a flow owned or proves physical-wire delivery.

Match the recorded client port to the actual probe socket through runner read-only inspection. Other client ports remain unowned. Repeated/zero IPIDs and identical lengths are ambiguous pairing hints, not unique packet identities. Do not subtract timestamps across hosts. Compare local capture boundaries with each host's local exchange/handling metadata, distinguish kernel send submission from received delivery, and retain the unchanged300ms device lease/100ms challenge/actual-loop-progress gates. One finite run is diagnostic evidence, not voice/network acceptance.
