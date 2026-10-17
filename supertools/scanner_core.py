"""AGFO Multi-Subnet Scanner: bounded IPv4 discovery without external packages.

Only explicit private/CGNAT IPv4 targets can be scanned. ICMP is not required:
accessible TCP services also identify an online host.
"""
from __future__ import annotations

import ipaddress
import errno
import selectors
import struct
import json
import os
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from threading import Event
from typing import Callable, Iterable, Optional

APP_VERSION = "1.7.0"
MAX_TARGETS = 2048
COMMON_PORTS = (445, 80, 443)
EXTENDED_PORTS = (445, 80, 443, 22, 21, 8080, 8443, 5000, 5001, 873, 2049)
PORT_LABELS = {
    445: "SMB", 80: "HTTP", 443: "HTTPS", 22: "SSH/SFTP", 21: "FTP",
    8080: "WEB:8080", 8443: "HTTPS:8443", 5000: "WEB:5000",
    5001: "HTTPS:5001", 873: "rsync", 2049: "NFS",
}
DEFAULT_SCOPES = ("192.168.0.0/24", "192.168.1.0/24")
OTHER_COMMON_SCOPES = ("192.168.2.0/24", "192.168.8.0/24", "192.168.10.0/24",
                       "192.168.50.0/24", "192.168.100.0/24", "10.0.0.0/24")
PRIVATE_CIDRS = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",
))


@dataclass(frozen=True)
class HostResult:
    ip: str
    ping: bool
    open_ports: tuple[int, ...]
    hostname: str = ""
    elapsed_ms: int = 0
    discovery: str = ""
    mac: str = ""
    verified: bool = True
    tcp_rejected: bool = False

    @property
    def detected_via(self) -> str:
        sources = []
        if self.ping:
            sources.append("ICMP")
        if self.open_ports:
            sources.append("TCP")
        elif self.tcp_rejected:
            sources.append("TCP-RST")
        if self.discovery:
            sources.append(self.discovery + (" (aday)" if not self.verified else ""))
        return "+".join(sources)

    @property
    def services(self) -> str:
        return ", ".join(PORT_LABELS.get(p, str(p)) for p in self.open_ports) or "-"


def is_allowed_target(ip: ipaddress.IPv4Address) -> bool:
    return any(ip in network for network in PRIVATE_CIDRS)


def parse_target_ranges(text: str, max_targets: int = MAX_TARGETS) -> tuple[list[str], list[str]]:
    """Return (targets, canonical CIDRs); reject public ranges, invalid input and huge scans."""
    if not text or not text.strip():
        raise ValueError("En az bir IPv4 adresi veya CIDR agi yazin.")
    seen = set()
    nets = []
    scopes = []
    count = 0
    text = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    for token in re.split(r"[,;\s]+", text.strip()):
        if not token:
            continue
        try:
            network = ipaddress.ip_network(token, strict=False)
        except ValueError as exc:
            raise ValueError("Gecersiz IP/CIDR: " + token) from exc
        if not isinstance(network, ipaddress.IPv4Network):
            raise ValueError("Yalniz IPv4 desteklenir: " + token)
        if not is_allowed_target(network.network_address) or not is_allowed_target(network.broadcast_address):
            raise ValueError("Guvenlik: Yalniz ozel IPv4 ve Tailscale/CGNAT aglari taranir: " + token)
        if network.num_addresses > max_targets + 2:
            raise ValueError("Cok buyuk ag: " + token + ". /24 gibi kucuk aglar secin.")
        normal = str(network)
        if normal not in nets:
            nets.append(normal)
        for addr in network.hosts():
            value = str(addr)
            if value not in seen:
                seen.add(value)
                scopes.append(value)
                count += 1
                if count > max_targets:
                    raise ValueError("Tek taramada en fazla %s IP taranabilir." % max_targets)
    if not scopes:
        raise ValueError("Taranacak kullanilabilir IP yok.")
    scopes.sort(key=lambda address: int(ipaddress.IPv4Address(address)))
    return scopes, nets


def _quick_cidr(ip_text: str, prefix: int = 24) -> Optional[str]:
    try:
        ip = ipaddress.ip_address(ip_text)
        if not isinstance(ip, ipaddress.IPv4Address) or not is_allowed_target(ip):
            return None
        network = ipaddress.ip_network("%s/%d" % (ip, prefix), strict=False)
        return str(network)
    except ValueError:
        return None


def hidden_process_options() -> dict:
    """Ensure console programs never flash an MSDOS window under pythonw.exe."""
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}


def hidden_run(argv: list[str], **kwargs):
    kwargs.update(hidden_process_options())
    return subprocess.run(argv, **kwargs)


def discover_windows_networks(timeout_seconds: int = 7) -> list[tuple[str, str]]:
    """Suggest bounded CIDRs using Windows interfaces, gateways and route table.

    A missing route does NOT mean a network is impossible to reach; the known
    .0/.1 blocks are included as manual candidates for common dual-router setups.
    """
    suggestions: dict[str, str] = {scope: "Sik gorulen yerel ag" for scope in DEFAULT_SCOPES}
    for scope in OTHER_COMMON_SCOPES:
        suggestions.setdefault(scope, "Diger yaygin router agi - secilirse taranir")
    if os.name != "nt":
        return list(suggestions.items())
    code = r'''
$ErrorActionPreference = 'SilentlyContinue'
$ips = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -and $_.AddressState -ne 'Tentative' } | Select-Object IPAddress, PrefixLength, InterfaceAlias)
$gws = @(Get-NetIPConfiguration | ForEach-Object { $_.IPv4DefaultGateway.NextHop } | Where-Object { $_ })
$routes = @(Get-NetRoute -AddressFamily IPv4 | Select-Object -ExpandProperty DestinationPrefix)
$dhcp = @(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=TRUE' | Select-Object -ExpandProperty DHCPServer | Where-Object { $_ })
@{ ips=$ips; gateways=$gws; routes=$routes; dhcp=$dhcp } | ConvertTo-Json -Compress -Depth 6
'''
    try:
        raw = hidden_run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", code],
            capture_output=True, timeout=timeout_seconds, check=False,
        )
        output = raw.stdout.decode("utf-8-sig", "replace")
        if not output.strip():
            # Windows PowerShell can emit text in the legacy code page.
            output = raw.stdout.decode("mbcs", "replace")
        data = json.loads(output)
        for item in data.get("ips", []):
            if not isinstance(item, dict):
                continue
            ip = item.get("IPAddress", "")
            prefix = item.get("PrefixLength", 24)
            try:
                prefix = max(24, min(32, int(prefix)))
            except (ValueError, TypeError):
                prefix = 24
            cidr = _quick_cidr(ip, prefix)
            if cidr:
                suggestions[cidr] = "Arayuz: " + str(item.get("InterfaceAlias", "Windows"))
        for gateway in data.get("gateways", []):
            cidr = _quick_cidr(gateway)
            if cidr:
                suggestions[cidr] = "Varsayilan ag gecidi"
        for server in data.get("dhcp", []):
            cidr = _quick_cidr(server)
            if cidr:
                suggestions[cidr] = "Windows DHCP sunucusu"
        for route in data.get("routes", []):
            try:
                network = ipaddress.ip_network(route, strict=False)
                if not isinstance(network, ipaddress.IPv4Network):
                    continue
                if network.prefixlen < 24:
                    continue  # avoid broad automatic scans
                if is_allowed_target(network.network_address) and is_allowed_target(network.broadcast_address):
                    suggestions.setdefault(str(network), "Windows route tablosu")
            except (ValueError, TypeError):
                continue
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        pass
    return sorted(suggestions.items(), key=lambda pair: int(ipaddress.IPv4Network(pair[0]).network_address))


def windows_native_ping(ip: str, timeout_ms: int) -> Optional[bool]:
    """Native Windows ICMP, without spawning a console on every address."""
    if os.name != "nt":
        return None
    handle = None
    try:
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("iphlpapi", use_last_error=True)
        api.IcmpCreateFile.restype = wintypes.HANDLE
        api.IcmpCloseHandle.argtypes = [wintypes.HANDLE]
        api.IcmpSendEcho.argtypes = [
            wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.WORD,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        ]
        api.IcmpSendEcho.restype = wintypes.DWORD
        handle = api.IcmpCreateFile()
        if not handle or handle == ctypes.c_void_p(-1).value:
            return None
        packet = ctypes.create_string_buffer(b"AGFOscan")
        answer = ctypes.create_string_buffer(256)
        destination = struct.unpack("<I", socket.inet_aton(ip))[0]
        replies = api.IcmpSendEcho(handle, destination, packet,
                                   len(packet.value), None, answer,
                                   len(answer), max(100, int(timeout_ms)))
        # The ICMP_ECHO_REPLY.Status field is at offset 4; IP_SUCCESS == 0.
        return bool(replies and struct.unpack_from("<I", answer, 4)[0] == 0)
    except (OSError, AttributeError, ValueError, TypeError):
        return None
    finally:
        if handle and handle != -1:
            try:
                api.IcmpCloseHandle(handle)
            except Exception:
                pass


def ping_host(ip: str, timeout_ms: int, cancel: Event) -> bool:
    if cancel.is_set():
        return False
    if os.name == "nt":
        direct = windows_native_ping(ip, timeout_ms)
        if direct is not None:
            return direct
        argv = ["ping.exe", "-n", "1", "-w", str(max(100, timeout_ms)), ip]
        timeout = max(1.4, timeout_ms / 1000.0 + 1.0)
    else:
        argv = ["ping", "-c", "1", "-W", "1", ip]
        timeout = 2.0
    try:
        completed = hidden_run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   stdin=subprocess.DEVNULL, timeout=timeout, check=False)
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def tcp_port_open(ip: str, port: int, timeout_seconds: float, cancel: Event) -> bool:
    if cancel.is_set():
        return False
    try:
        with socket.create_connection((ip, port), timeout=timeout_seconds):
            return True
    except (OSError, ValueError):
        return False


def tcp_probe_ports(ip: str, ports: Iterable[int], timeout_seconds: float, cancel: Event,
                    details: bool = False):
    """Probe multiple ports concurrently per IP (one deadline, not N timeouts)."""
    if cancel.is_set():
        return ((), False) if details else ()
    refused = False
    reject_codes = {errno.ECONNREFUSED, getattr(errno, "WSAECONNREFUSED", 10061)}
    allowed_errors = {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY,
                      getattr(errno, "WSAEWOULDBLOCK", 10035),
                      getattr(errno, "WSAEINPROGRESS", 10036),
                      getattr(errno, "WSAEALREADY", 10037)}
    succeeded: set[int] = set()
    with selectors.DefaultSelector() as selector:
        try:
            for port in ports:
                if cancel.is_set():
                    break
                port = int(port)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    sock.setblocking(False)
                    rc = sock.connect_ex((ip, port))
                    if rc == 0:
                        succeeded.add(port)
                        sock.close()
                    elif rc in allowed_errors:
                        selector.register(sock, selectors.EVENT_WRITE, port)
                    else:
                        if rc in reject_codes:
                            refused = True
                        sock.close()
                except OSError:
                    sock.close()
            expiry = time.monotonic() + max(.1, timeout_seconds)
            while selector.get_map() and not cancel.is_set():
                remaining = expiry - time.monotonic()
                if remaining <= 0:
                    break
                for key, _ in selector.select(min(.1, remaining)):
                    sock = key.fileobj
                    try:
                        code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                        if code == 0:
                            succeeded.add(key.data)
                        elif code in reject_codes:
                            refused = True
                    except OSError:
                        pass
                    selector.unregister(sock)
                    sock.close()
        finally:
            # selectors.close() does not close registered sockets by itself.
            for key in list(selector.get_map().values()):
                try:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                except OSError:
                    pass
    opened = tuple(int(p) for p in ports if int(p) in succeeded)
    return (opened, refused) if details else opened


# 'arp -a' also shows discovered hosts that have no visible TCP services.
# These are suggestions, not proofs that a device is currently powered on.
def parse_arp_neighbors(output: str) -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    for line in output.splitlines():
        match = re.search(r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+"
                          r"([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\s+"
                          r"(dynamic|dinamik|static|statik)\b", line, re.I)
        if not match:
            continue
        try:
            addr = ipaddress.ip_address(match.group(1))
            if not isinstance(addr, ipaddress.IPv4Address) or not is_allowed_target(addr):
                continue
            if match.group(2).lower() == "ff-ff-ff-ff-ff-ff":
                continue
            if match.group(3).lower() in ("static", "statik"):
                continue
        except ValueError:
            continue
        found[str(addr)] = ("ARP", match.group(2).replace(":", "-").upper())
    return found


def discover_arp_neighbors(timeout_seconds: int = 5) -> dict[str, tuple[str, str]]:
    if os.name != "nt":
        return {}
    try:
        run = hidden_run(["arp.exe", "-a"], capture_output=True,
                         stdin=subprocess.DEVNULL, timeout=timeout_seconds, check=False)
        return parse_arp_neighbors(run.stdout.decode("mbcs", "replace"))
    except (OSError, subprocess.TimeoutExpired, LookupError):
        return {}


def discover_multicast_neighbors(timeout_seconds: float = 1.6,
                                 cancel: Optional[Event] = None) -> dict[str, tuple[str, str]]:
    """Local SSDP and mDNS discovery, with TTL=1; does not cross NAT."""
    cancel = cancel or Event()
    if cancel.is_set():
        return {}
    found: dict[str, tuple[str, str]] = {}
    probes = (
        ("SSDP", "239.255.255.250", 1900, b"M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 1\r\nST: ssdp:all\r\n\r\n"),
        ("mDNS", "224.0.0.251", 5353,
         b"\x00\x01\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" +
         b"\x09_services\x07_dns-sd\x04_udp\x05local\x00\x00\x0c\x80\x01"),
    )
    with selectors.DefaultSelector() as selector:
        try:
            for method, dest, port, packet in probes:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                    sock.bind(("0.0.0.0", 0))
                    sock.setblocking(False)
                    sock.sendto(packet, (dest, port))
                    selector.register(sock, selectors.EVENT_READ, method)
                except OSError:
                    sock.close()
            expiry = time.monotonic() + max(.2, min(3.5, timeout_seconds))
            while selector.get_map() and not cancel.is_set():
                remaining = expiry - time.monotonic()
                if remaining <= 0:
                    break
                for key, _ in selector.select(min(.15, remaining)):
                    try:
                        packet, sender = key.fileobj.recvfrom(4096)
                        source_ip = sender[0]
                        addr = ipaddress.ip_address(source_ip)
                        if packet and isinstance(addr, ipaddress.IPv4Address) and is_allowed_target(addr):
                            found[source_ip] = (key.data, "")
                    except (OSError, ValueError, TypeError):
                        continue
        finally:
            for key in list(selector.get_map().values()):
                try:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                except OSError:
                    pass
    return found


def discover_neighbor_candidates(targets: Iterable[str], cancel: Event,
                                 include_multicast: bool = True) -> dict[str, tuple[str, str]]:
    allowed = set(targets)
    hints = {ip: entry for ip, entry in discover_arp_neighbors().items() if ip in allowed}
    if include_multicast and not cancel.is_set():
        for ip, entry in discover_multicast_neighbors(cancel=cancel).items():
            if ip in allowed:
                previous = hints.get(ip)
                hints[ip] = ((previous[0] + "+" + entry[0]) if previous else entry[0],
                             previous[1] if previous else entry[1])
    return hints


def reverse_dns(ip: str) -> str:
    try:
        name = socket.gethostbyaddr(ip)[0]
        return name if name != ip else ""
    except (socket.herror, socket.gaierror, OSError):
        return ""


def scan_one(ip: str, ports: Iterable[int], timeout_ms: int, cancel: Event,
             resolve_hostname: bool = False) -> Optional[HostResult]:
    if cancel.is_set():
        return None
    started = time.monotonic()
    responds = ping_host(ip, timeout_ms, cancel)
    open_ports, refused = tcp_probe_ports(ip, ports, timeout_ms / 1000.0, cancel, details=True)
    if cancel.is_set() or not (responds or open_ports or refused):
        return None
    hostname = reverse_dns(ip) if resolve_hostname else ""
    return HostResult(ip, responds, open_ports, hostname,
                      int((time.monotonic() - started) * 1000), tcp_rejected=refused)


def scan_targets(targets: list[str], extended: bool, timeout_ms: int, workers: int,
                 cancel: Event, on_progress: Callable[[int, int, Optional[HostResult]], None],
                 resolve_hostname: bool = False,
                 candidates: Optional[dict[str, tuple[str, str]]] = None) -> int:
    """Parallel read-only probing with candidate-first ordering and bounded second pass.

    'candidate' rows without ICMP/TCP confirmation are explicitly marked as
    unverified, never counted as confirmed devices.
    """
    workers = max(1, min(96, int(workers)))
    timeout_ms = max(100, min(2500, int(timeout_ms)))
    ports = EXTENDED_PORTS if extended else COMMON_PORTS
    allow_extra_discovery = candidates is not None
    candidates = dict(candidates or {})
    targets = list(dict.fromkeys(targets))
    target_set = set(targets)
    prioritized = [ip for ip in candidates if ip in target_set]
    todo = prioritized + [ip for ip in targets if ip not in candidates]
    total = len(todo)
    completed = 0
    results = set()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="agfo-scan") as executor:
        futures = {executor.submit(scan_one, ip, ports, timeout_ms, cancel, resolve_hostname): ip for ip in todo}
        for future in as_completed(futures):
            ip = futures[future]
            completed += 1
            try:
                result = future.result()
            except Exception:
                result = None
            if result:
                results.add(ip)
                if ip in candidates:
                    label, mac = candidates[ip]
                    result = replace(result, discovery=label, mac=mac)
            on_progress(completed, total, result)
            if cancel.is_set():
                for pending in futures:
                    pending.cancel()
                break
    if cancel.is_set():
        return len(results)

    # The active scan may have populated ARP with previously unknown local
    # neighbors. Re-read it AFTER the sweep as well (bounded and read-only).
    if allow_extra_discovery:
        for ip, value in discover_arp_neighbors().items():
            if ip in target_set and ip not in candidates:
                candidates[ip] = value
                prioritized.append(ip)
    # Candidate hosts that were seen in ARP/multicast often warrant one longer
    # probe; do not retry every address or introduce large unattended delays.
    retry = [ip for ip in prioritized if ip not in results][:64]
    if retry:
        with ThreadPoolExecutor(max_workers=min(workers, 24), thread_name_prefix="agfo-retry") as executor:
            futures = {executor.submit(scan_one, ip, ports, max(850, timeout_ms),
                                       cancel, resolve_hostname): ip for ip in retry}
            for future in as_completed(futures):
                ip = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = None
                if result:
                    results.add(ip)
                    label, mac = candidates[ip]
                    on_progress(total, total, replace(result, discovery=label, mac=mac))
                if cancel.is_set():
                    break
    if not cancel.is_set():
        for ip in prioritized:
            if ip not in results:
                label, mac = candidates[ip]
                on_progress(total, total, HostResult(ip, False, (), discovery=label,
                                                     mac=mac, verified=False))
    return len(results)


@dataclass(frozen=True)
class ShareQueryResult:
    text: str
    access_denied: bool = False
    return_code: int = 0


def decode_windows_net_output(raw: bytes) -> str:
    """Decode Windows console utilities with OEM rather than the ANSI code page.

    net.exe/route.exe/arp.exe generally write to the OEM console code page.
    A Turkish Windows installation often uses cp857, not mbcs/cp1254.
    """
    if not raw:
        return ""
    if os.name != "nt":
        return raw.decode("utf-8", "replace")
    try:
        import ctypes
        cp = ctypes.windll.kernel32.GetOEMCP()
        encoding = "cp" + str(cp)
        return raw.decode(encoding, "replace")
    except (LookupError, AttributeError, OSError, ValueError):
        return raw.decode("mbcs", "replace")


def is_smb_access_denied(output: str) -> bool:
    """Recognize Turkish and English Windows error 5 regardless of net.exe exit status."""
    s = output.casefold()
    return bool(re.search(r"\b(?:system error\s*5|sistem hatas\S*\s*5|5\s+sistem hatas\S*)\b", s)
                or "access is denied" in s or "erişim engellendi" in s
                or "erişim reddedildi" in s)


def query_windows_shares(ip: str, timeout_seconds: int = 8) -> ShareQueryResult:
    """Enumerate readable share names, never silently claiming access from an open TCP port."""
    if os.name != "nt":
        return ShareQueryResult("Bu özellik Windows'ta çalışır.")
    addr = ipaddress.ip_address(ip)
    if not isinstance(addr, ipaddress.IPv4Address) or not is_allowed_target(addr):
        raise ValueError("Özel IPv4 adresi seçin.")
    try:
        process = hidden_run(["net.exe", "view", '\\\\' + ip],
                             capture_output=True, timeout=timeout_seconds,
                             stdin=subprocess.DEVNULL, check=False)
        output = "\n".join(part for part in (
            decode_windows_net_output(process.stdout).strip(),
            decode_windows_net_output(process.stderr).strip()) if part)
        denied = is_smb_access_denied(output)
        if denied:
            msg = ("SMB servisine ulaşılıyor ancak paylaşım listesini okuma izni yok (hata 5). "
                   "Bu, NAS'ın çevrimdışı olduğu anlamına gelmez. "
                   "NAS oturumu açabilir veya adını bildiğiniz paylaşıma doğrudan bağlanabilirsiniz.")
            return ShareQueryResult(msg + ("\n\nWindows çıktısı:\n" + output if output else ""),
                                    True, process.returncode)
        return ShareQueryResult(output or "net view boş yanıt verdi.", False, process.returncode)
    except subprocess.TimeoutExpired:
        return ShareQueryResult("Zaman aşımı: SMB portu açık olsa bile listeleme engellenebilir.", False, -1)
    except OSError as exc:
        return ShareQueryResult("net view başlatılamadı: " + str(exc), False, -1)


def windows_share_list(ip: str, timeout_seconds: int = 8) -> str:
    """Backward-compatible text-only wrapper for legacy integrations."""
    return query_windows_shares(ip, timeout_seconds).text


def validate_smb_share(share: str) -> str:
    """A blank name targets IPC$ for share enumeration. Never accept UNC injection."""
    share = (share or "").strip()
    if not share:
        return "IPC$"
    if len(share) > 80 or share in (".", "..") or any(c in share for c in '\\/:*?"<>|'):
        raise ValueError("Geçersiz SMB paylaşım adı. Sadece tek paylaşım adı yazın.")
    if any(ord(c) < 32 for c in share):
        raise ValueError("Paylaşım adında kontrol karakteri olamaz.")
    return share


def _connect_windows_smb(remote: str, user: str, password: str) -> int:
    """Open a Windows SMB session without exposing passwords in process arguments.

    WNetAddConnection2W is non-persistent here (dwFlags=0). Windows can still
    retain an authenticated session in memory until it is disconnected/logged off.
    """
    import ctypes
    from ctypes import wintypes

    class NETRESOURCEW(ctypes.Structure):
        _fields_ = [
            ("dwScope", wintypes.DWORD), ("dwType", wintypes.DWORD),
            ("dwDisplayType", wintypes.DWORD), ("dwUsage", wintypes.DWORD),
            ("lpLocalName", wintypes.LPWSTR), ("lpRemoteName", wintypes.LPWSTR),
            ("lpComment", wintypes.LPWSTR), ("lpProvider", wintypes.LPWSTR),
        ]

    netresource = NETRESOURCEW()
    netresource.dwType = 1  # RESOURCETYPE_DISK
    netresource.lpRemoteName = remote
    mpr = ctypes.WinDLL("mpr", use_last_error=True)
    fn = mpr.WNetAddConnection2W
    fn.argtypes = [ctypes.POINTER(NETRESOURCEW), wintypes.LPCWSTR,
                   wintypes.LPCWSTR, wintypes.DWORD]
    fn.restype = wintypes.DWORD
    # This session is not persisted into the Windows user profile.
    return int(fn(ctypes.byref(netresource), password, user, 0))


def connect_smb_session(ip: str, share: str, user: str, password: str, connector=None) -> int:
    """Open a Windows SMB session for a specific share or IPC$.

    Passwords must never be logged, serialized or passed to net.exe arguments.
    """
    if os.name != "nt" and connector is None:
        raise OSError("SMB oturum açma yalnızca Windows'ta kullanılabilir.")
    addr = ipaddress.ip_address(ip)
    if not isinstance(addr, ipaddress.IPv4Address) or not is_allowed_target(addr):
        raise ValueError("Özel IPv4 adresi seçin.")
    name = validate_smb_share(share)
    user = (user or "").strip()
    if not user:
        raise ValueError("NAS kullanıcı adını girin.")
    if len(user) > 256 or any(ord(c) < 32 for c in user):
        raise ValueError("Geçersiz kullanıcı adı.")
    remote = '\\\\' + ip + '\\' + name
    return (connector or _connect_windows_smb)(remote, user, password)


def explain_smb_error(code: int) -> str:
    messages = {
        5: "Erişim reddedildi. NAS kullanıcı ve paylaşım izinlerini kontrol edin.",
        53: "Ağ yolu bulunamadı. NAS erişimini ve SMB servisini kontrol edin.",
        67: "Ağ paylaşım adı bulunamadı. Paylaşım adını doğrulayın.",
        86: "Parola kabul edilmedi. NAS parolasını doğrulayın.",
        1219: ("Windows bu NAS'a başka bir kullanıcıyla zaten bağlı (hata 1219). "
               "Mevcut SMB oturumlarını inceleyin; uygulama onları otomatik sonlandırmaz."),
        1326: "Oturum açma başarısız. NAS kullanıcı adı/parolasını doğrulayın.",
    }
    return messages.get(code, "Windows SMB bağlantı hatası: " + str(code))
