# -*- coding: utf-8 -*-
"""AGFO SuperTools: explicit, bounded network diagnostics. Python stdlib only.

No background polling, shell interpolation, automatic authentication or write-side
operations. Operations can reach public hosts only after the user runs a test.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import ip_address
import json
import re
import shutil
import smtplib
import socket
import ssl
import subprocess
import threading
import time
from typing import Optional
from urllib import request, error, parse

import scanner_core as scanner

DNS_TYPES = ("A", "AAAA", "MX", "NS", "CNAME", "TXT", "SOA", "PTR", "SRV", "CAA")
TOOL_OPTIONS = (
    "DNS A", "DNS AAAA", "DNS MX", "DNS NS", "DNS TXT", "DNS CNAME",
    "DNS SOA", "DNS PTR", "DNS SRV", "DNS CAA", "SPF", "DKIM", "DMARC",
    "MTA-STS", "TLS-RPT", "Mail Sağlığı", "TCP Port", "Ping", "Traceroute", "HTTP", "HTTPS",
    "TLS Sertifikası", "SMTP / STARTTLS", "RDAP / ASN",
)
PREFIXES = {
    "a": "DNS A", "aaaa": "DNS AAAA", "mx": "DNS MX", "ns": "DNS NS",
    "txt": "DNS TXT", "cname": "DNS CNAME", "soa": "DNS SOA", "ptr": "DNS PTR",
    "srv": "DNS SRV", "caa": "DNS CAA", "spf": "SPF", "dkim": "DKIM",
    "dmarc": "DMARC", "mtasts": "MTA-STS", "tlsrpt": "TLS-RPT", "mail": "Mail Sağlığı", "tcp": "TCP Port", "ping": "Ping",
    "trace": "Traceroute", "tracert": "Traceroute", "http": "HTTP",
    "https": "HTTPS", "tls": "TLS Sertifikası", "smtp": "SMTP / STARTTLS",
    "rdap": "RDAP / ASN",
}

MAX_HOST_LENGTH = 253
MAX_TEXT = 96 * 1024


@dataclass(frozen=True)
class DiagnosticResult:
    label: str
    target: str
    content: str
    success: bool
    elapsed_ms: int
    timestamp: str


class DiagnosticError(ValueError):
    pass


def normalize_host(value: str) -> str:
    """Validate one IP or DNS name; no userinfo, port, shell, control chars."""
    if not isinstance(value, str):
        raise DiagnosticError("Geçersiz sunucu veya alan adı.")
    raw = value.strip().rstrip(".")
    if not raw or len(raw) > MAX_HOST_LENGTH or any(c.isspace() for c in raw):
        raise DiagnosticError("Alan adı/IP boş veya geçersiz.")
    if any(ch in raw for ch in ("/", "\\", "@", "#", "?", "'", '"', "$", "%", ";", "=", "[", "]")):
        raise DiagnosticError("Sunucu adında geçersiz karakter var.")
    try:
        return str(ip_address(raw))
    except ValueError:
        pass
    try:
        name = raw.encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError) as exc:
        raise DiagnosticError("Alan adı IDNA biçimine çevrilemedi.") from exc
    if not re.fullmatch(r"[a-z0-9_.:-]+", name) or len(name) > 253:
        raise DiagnosticError("Sunucu/alan adı hatalı.")
    if ':' in name:  # IPv6 literals are handled by ip_address above.
        raise DiagnosticError("Portu sunucu adıyla birleştirmeyin; ayrı alan kullanın.")
    if not all(re.fullmatch(r"[a-z0-9_-]{1,63}", item) for item in name.split('.')):
        raise DiagnosticError("Alan adında geçersiz etiket var.")
    if name.startswith('-') or any(item.startswith('-') or item.endswith('-') for item in name.split('.')):
        raise DiagnosticError("Alan adı hatalı.")
    return name


def host_port(value: str, default: int) -> tuple[str, int]:
    s = value.strip()
    if not s:
        raise DiagnosticError("Sunucu adı/IP gerekli.")
    if s.startswith("["):
        m = re.fullmatch(r"\[([^\]]+)\](?::(\d{1,5}))?", s)
        if not m:
            raise DiagnosticError("IPv6 port biçimi: [adres]:port")
        host = normalize_host(m.group(1))
        port = int(m.group(2) or default)
    elif s.count(":") == 1 and re.search(r":\d{1,5}$", s):
        h, p = s.rsplit(":", 1)
        host, port = normalize_host(h), int(p)
    else:
        host, port = normalize_host(s), default
    if not 1 <= port <= 65535:
        raise DiagnosticError("Port 1-65535 aralığında olmalı.")
    return host, port


def sanitize_target(tool: str, value: str) -> str:
    """Return display target after tool-specific parsing."""
    if tool not in TOOL_OPTIONS:
        raise DiagnosticError("Tanımlanmayan test: " + str(tool))
    if tool in ("HTTP", "HTTPS"):
        return normalize_url(value, tool == "HTTPS")
    if tool == "DKIM":
        # Accept selector:example.com or selector._domainkey.example.com.
        raw = value.strip()
        if ":" in raw and not raw.startswith("["):
            selector, domain = raw.split(":", 1)
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", selector):
                raise DiagnosticError("DKIM seçicisi (selector) geçersiz.")
            return normalize_host(selector + "._domainkey." + normalize_host(domain))
        target = normalize_host(raw)
        if "._domainkey." not in target:
            raise DiagnosticError("DKIM için selector:alanadi.com yazın.")
        return target
    if tool in ("TCP Port", "TLS Sertifikası", "SMTP / STARTTLS"):
        default = {"TCP Port": 443, "TLS Sertifikası": 443, "SMTP / STARTTLS": 587}[tool]
        host, port = host_port(value, default)
        if tool == "TCP Port" and ":" not in value:
            raise DiagnosticError("TCP testi için sunucu:port yazın.")
        return f"[{host}]:{port}" if ':' in host else f"{host}:{port}"
    host = normalize_host(value)
    if tool == "DMARC":
        if not host.startswith("_dmarc."):
            host = "_dmarc." + host
    if tool == "MTA-STS" and not host.startswith("_mta-sts."):
        host = "_mta-sts." + host
    if tool == "TLS-RPT" and not host.startswith("_smtp._tls."):
        host = "_smtp._tls." + host
    if tool == "SPF" and host.startswith("_dmarc."):
        raise DiagnosticError("SPF için doğrudan alan adını girin.")
    if tool == "RDAP / ASN":
        try:
            address = ip_address(host)
        except ValueError as exc:
            raise DiagnosticError("RDAP için IP adresi girin; alan adını önce DNS ile çözün.") from exc
        if not address.is_global:
            raise DiagnosticError("Özel ağ IP'leri için genel RDAP sorgusu desteklenmez.")
    return host


def parse_command(value: str, selected_tool: str) -> tuple[str, str]:
    """MXToolbox-like command field: 'mx: example.com'."""
    raw = value.strip()
    m = re.match(r"^([a-zA-Z]{1,9}):\s*(.+)$", raw)
    if not raw.lower().startswith(("http://", "https://")) and m and m.group(1).lower() in PREFIXES:
        return PREFIXES[m.group(1).lower()], m.group(2).strip()
    return selected_tool, raw


def normalize_url(value: str, prefer_https: bool) -> str:
    value = value.strip()
    if not value:
        raise DiagnosticError("URL gerekli.")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value):
        if not value.lower().startswith(("http://", "https://")):
            raise DiagnosticError("Yalnızca HTTP ve HTTPS adresleri desteklenir.")
    else:
        value = ("https://" if prefer_https else "http://") + value
    parts = parse.urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise DiagnosticError("Yalnızca kullanıcı/parola içermeyen HTTP(S) adresleri kullanılabilir.")
    if len(value) > 2048 or "\n" in value or "\r" in value:
        raise DiagnosticError("URL fazla uzun veya hatalı.")
    try:
        host = normalize_host(parts.hostname)
        port = parts.port
    except ValueError as exc:
        raise DiagnosticError("URL portu geçersiz.") from exc
    # Keep the source URL intact except for validation; urllib encodes the request path.
    if not host or port == 0:
        raise DiagnosticError("URL sunucusu geçersiz.")
    return value


def _native_result(args: list[str], timeout: float) -> str:
    try:
        p = scanner.hidden_run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=timeout, check=False)
    except FileNotFoundError:
        raise DiagnosticError("Windows komutu bulunamadı: " + args[0])
    except subprocess.TimeoutExpired as exc:
        raise DiagnosticError("Komut zaman aşımına uğradı (%.0f sn)." % timeout) from exc
    raw = p.stdout or b""
    if isinstance(raw, bytes):
        output = scanner.decode_windows_net_output(raw)
    else:
        output = str(raw)
    output = output.strip()
    if p.returncode:
        raise DiagnosticError("Komut hata kodu %d:\n%s" % (p.returncode, output or "Yanıt yok."))
    return output or "Yanıt yok."


def _dns_lookup(qtype: str, host: str, timeout: float) -> str:
    # System resolver, no external packages or hardcoded public DNS required.
    # Windows nslookup accepts '-type=MX', '-timeout=3', '-retry=1'.
    # PTR accepts address and returns reverse name (nslookup -type=PTR x.x.x.x).
    host = normalize_host(host)
    if not shutil.which("nslookup"):
        if qtype in ("A", "AAAA"):
            af = socket.AF_INET6 if qtype == "AAAA" else socket.AF_INET
            records = sorted(set(item[4][0] for item in socket.getaddrinfo(host, None, af)))
            return "\n".join(records) if records else "DNS kaydı bulunamadı."
        raise DiagnosticError("nslookup.exe bulunamadı; Windows DNS istemcisini kontrol edin.")
    return _native_result(["nslookup", "-timeout=3", "-retry=1", "-type=" + qtype, host], min(12, timeout))


def _tcp_check(host: str, port: int, timeout: float) -> str:
    with socket.create_connection((host, port), timeout=timeout):
        pass
    return f"BAŞARILI: {host}:{port} TCP bağlantısı kabul edildi."


def _tls_cert(host: str, port: int, timeout: float) -> str:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as secured:
            cert = secured.getpeercert()
            subject = ", ".join("=".join(pair) for group in cert.get("subject", ()) for pair in group)
            issuer = ", ".join("=".join(pair) for group in cert.get("issuer", ()) for pair in group)
            expires = cert.get("notAfter", "")
            days = None
            if expires:
                days = int((ssl.cert_time_to_seconds(expires) - time.time()) // 86400)
            san = ", ".join("%s:%s" % p for p in cert.get("subjectAltName", ())[:12])
            return (f"TLS: {secured.version()}\nŞifre: {secured.cipher()[0]}\n"
                    f"Subject: {subject}\nIssuer: {issuer}\nBitiş: {expires}\n"
                    f"Kalan gün: {days if days is not None else '?'}\nSAN (ilk 12): {san}\n"
                    "Sertifika zinciri ve sunucu adı varsayılan güven köklerine göre doğrulandı.")


def _http_check(url: str, timeout: float) -> str:
    r = request.Request(url, headers={"User-Agent": "AGFO-SuperTools/1.3", "Accept": "*/*"}, method="HEAD")
    try:
        with request.urlopen(r, timeout=timeout) as resp:
            return _http_details(resp)
    except error.HTTPError as exc:
        if exc.code in (405, 501):
            r = request.Request(url, headers={"User-Agent": "AGFO-SuperTools/1.3", "Range": "bytes=0-1023"}, method="GET")
            with request.urlopen(r, timeout=timeout) as resp:
                return _http_details(resp)
        return "HTTP %d %s\n%s" % (exc.code, exc.reason, _header_lines(exc.headers))


def _header_lines(headers) -> str:
    selected = ("content-type", "content-length", "server", "location", "strict-transport-security",
                "content-security-policy", "x-frame-options", "cache-control")
    return "\n".join("%s: %s" % (h, str(headers[h])[:200]) for h in selected if h in headers)


def _http_details(resp) -> str:
    return "HTTP %d %s\nSon URL: %s\n%s" % (
        resp.status, resp.reason, resp.geturl(), _header_lines(resp.headers))


def _smtp_test(host: str, port: int, timeout: float) -> str:
    """Read-only SMTP handshake; no username/password, MAIL FROM or RCPT TO."""
    context = ssl.create_default_context()
    client = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) if port == 465 else smtplib.SMTP(host, port, timeout=timeout)
    try:
        code, message = client.ehlo("agfo-diagnostic.local")
        response = [f"EHLO {code}: {message[:300].decode('utf-8', 'replace') if isinstance(message, bytes) else str(message)[:300]}"]
        if code >= 400:
            return "\n".join(response) + "\nSunucu EHLO isteğini reddetti."
        features = sorted(client.esmtp_features.keys())
        response.append("Desteklenen ESMTP: " + (", ".join(features) or "-") )
        if port != 465 and client.has_extn("starttls"):
            client.starttls(context=context)
            code, _ = client.ehlo("agfo-diagnostic.local")
            response.append(f"STARTTLS başarılı, yeniden EHLO: {code}")
        elif port == 465:
            response.append("TLS: SMTPS (bağlantı başından itibaren şifreli)")
        else:
            response.append("STARTTLS sunucu tarafından ilan edilmedi. Bağlantı açık metin olabilir.")
        response.append("E-posta gönderilmedi; yalnızca sunucu el sıkışması test edildi.")
        return "\n".join(response)
    finally:
        try:
            client.quit()
        except (smtplib.SMTPException, OSError):
            client.close()


def _rdap_check(host: str, timeout: float) -> str:
    # Explicit public Internet request; never forward private addresses to RDAP.
    ip = ip_address(host)
    if not ip.is_global:
        raise DiagnosticError("Özel ağ adresi RDAP üzerinden aranmaz.")
    url = "https://rdap.org/ip/" + str(ip)
    r = request.Request(url, headers={"User-Agent": "AGFO-SuperTools/1.3", "Accept": "application/rdap+json"})
    with request.urlopen(r, timeout=timeout) as response:
        obj = json.loads(response.read(192 * 1024 + 1))
    if not isinstance(obj, dict):
        raise DiagnosticError("RDAP yanıtı geçersiz.")
    data = {key: obj.get(key) for key in ("name", "handle", "type", "startAddress", "endAddress", "country", "port43") if obj.get(key)}
    notices = obj.get("remarks") or []
    if isinstance(notices, list):
        data["açıklamalar"] = [x.get("description", []) for x in notices[:3] if isinstance(x, dict)]
    output = "RDAP kayıt özeti:\n" + json.dumps(data, ensure_ascii=False, indent=2)
    ripe_url = "https://stat.ripe.net/data/network-info/data.json?resource=" + parse.quote(str(ip), safe="")
    req = request.Request(ripe_url, headers={"User-Agent": "AGFO-SuperTools/1.3"})
    try:
        with request.urlopen(req, timeout=timeout) as response:
            ripe = json.loads(response.read(96 * 1024 + 1))
        if isinstance(ripe, dict) and isinstance(ripe.get("data"), dict):
            network = ripe["data"]
            asns = network.get("asns", [])
            prefix = network.get("prefix", "")
            output += "\n\nRIPEstat ağ/ASN:\nASN: %s\nPrefix: %s" % (", ".join("AS"+str(x) for x in asns), prefix)
    except (OSError, ValueError, error.URLError) as exc:
        output += "\n\nRIPEstat ASN sorgusu alınamadı: " + str(exc)
    return output


def run_diagnostic(tool: str, target: str, timeout: float = 8.0) -> DiagnosticResult:
    """One explicit diagnostic. Exceptions become transparent tool failures."""
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    start = time.monotonic()
    clean = sanitize_target(tool, target)
    timeout = max(2.0, min(float(timeout), 15.0))
    success = True
    try:
        if tool.startswith("DNS "):
            qtype = tool[4:]
            if qtype == "PTR":
                # Caller may enter 1.2.3.4; nslookup -type=PTR 1.2.3.4 handles it.
                pass
            content = _dns_lookup(qtype, clean, timeout)
        elif tool in ("SPF", "DKIM", "DMARC", "MTA-STS", "TLS-RPT"):
            content = _dns_lookup("TXT", clean, timeout)
            if tool == "SPF":
                content += "\n\nSPF aranan ifade: v=spf1"
            elif tool == "DMARC":
                content += "\n\nDMARC aranan ifade: v=DMARC1"
            elif tool == "MTA-STS":
                content += "\n\nMTA-STS DNS ifadesi: v=STSv1"
                domain = clean.removeprefix("_mta-sts.")
                try:
                    policy_url = "https://mta-sts." + domain + "/.well-known/mta-sts.txt"
                    with request.urlopen(request.Request(policy_url, headers={"User-Agent":"AGFO-SuperTools/1.3"}),timeout=timeout) as response:
                        policy = response.read(20 * 1024 + 1)
                    content += "\n\nMTA-STS politika dosyası:\n" + policy[:20*1024].decode("utf-8", "replace")
                except (OSError, error.URLError, ValueError) as exc:
                    content += "\n\nPolitika dosyası alınamadı: " + str(exc)
                    success = False
            elif tool == "TLS-RPT":
                content += "\n\nTLS-RPT DNS ifadesi: v=TLSRPTv1"
        elif tool == "Mail Sağlığı":
            sections = []
            for name, domain in (("MX", clean), ("SPF / TXT", clean), ("DMARC / TXT", "_dmarc." + clean)):
                kind = "MX" if name == "MX" else "TXT"
                try:
                    sections.append("==== " + name + " ====\n" + _dns_lookup(kind, domain, timeout))
                except (DiagnosticError, OSError, socket.error) as exc:
                    sections.append("==== " + name + " ====\nHATA: " + str(exc))
                    success = False
            content = "\n\n".join(sections)
        elif tool == "TCP Port":
            h, p = host_port(clean, 443)
            content = _tcp_check(h, p, timeout)
        elif tool == "Ping":
            result = scanner.ping_host(clean, int(timeout * 1000), threading.Event())
            content = "ICMP başarılı: yanıt alındı." if result else "ICMP yanıtı alınamadı; cihaz kapalı olmak zorunda değil."
            success = result
        elif tool == "Traceroute":
            if shutil.which("tracert"):
                content = _native_result(["tracert", "-d", "-h", "12", "-w", "450", clean], 20)
            elif shutil.which("traceroute"):
                content = _native_result(["traceroute", "-n", "-m", "12", "-w", "1", clean], 20)
            else:
                raise DiagnosticError("Traceroute aracı bulunamadı.")
        elif tool in ("HTTP", "HTTPS"):
            content = _http_check(clean, timeout)
            if content.startswith("HTTP 4") or content.startswith("HTTP 5"):
                success = False
        elif tool == "TLS Sertifikası":
            h, p = host_port(clean, 443)
            content = _tls_cert(h, p, timeout)
        elif tool == "SMTP / STARTTLS":
            h, p = host_port(clean, 587)
            content = _smtp_test(h, p, timeout)
        elif tool == "RDAP / ASN":
            content = _rdap_check(clean, timeout)
        else:
            raise DiagnosticError("Geçersiz test türü.")
    except (DiagnosticError, OSError, socket.error, ssl.SSLError, error.URLError,
            smtplib.SMTPException, ValueError, TimeoutError) as exc:
        success = False
        content = "HATA: " + str(exc)
    elapsed = round((time.monotonic() - start) * 1000)
    return DiagnosticResult(tool, clean, content[:MAX_TEXT], success, elapsed, ts)
