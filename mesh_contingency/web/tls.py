"""The remote console's HTTPS certificate.

Unless [console] names your own (cert and key), the bot makes one itself the
first time the remote console starts, in console_tls/ next to config.toml:
cert.pem and key.pem, an EC P-256 key, self-signed, valid 10 years, naming
this computer's hostname, <hostname>.local, localhost and its current
addresses. It works with no internet. Browsers warn about it once each;
whoever opens it checks the fingerprint the bot prints (and the local
console's Dashboard shows) against the one the browser shows.

mesh-contingency-console cert renew makes a new one (say this computer's
address changed); the bot uses it from its next start, and browsers warn
once again. cert show prints the fingerprint.

Needs the cryptography package, in the console extra.
"""

import datetime
import hashlib
import ipaddress
import os
import socket
import ssl
from pathlib import Path

TLS_FOLDER = "console_tls"
CERT_FILE = "cert.pem"
KEY_FILE = "key.pem"
VALID_DAYS = 3650


class CertificateError(Exception):
    """A certificate that can't be made or used; the message says why."""


def cryptography_missing():
    try:
        import cryptography  # noqa: F401
    except ImportError:
        return True
    return False


def tls_folder(config_folder):
    return Path(config_folder) / TLS_FOLDER


def own_addresses():
    """This computer's addresses other computers may use: those its hostname
    resolves to, and the one it reaches the network from (no packet is sent)."""
    found = set()
    try:
        for *_, sockaddr in socket.getaddrinfo(socket.gethostname(), None):
            found.add(sockaddr[0])
    except OSError:
        pass
    for family, probe in ((socket.AF_INET, "192.0.2.1"), (socket.AF_INET6, "2001:db8::1")):
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as s:
                s.connect((probe, 9))
                found.add(s.getsockname()[0])
        except OSError:
            pass
    addresses = []
    for text in found:
        try:
            address = ipaddress.ip_address(text.split("%", 1)[0])
        except ValueError:
            continue
        if not (address.is_loopback or address.is_unspecified or address.is_multicast):
            addresses.append(address)
    return sorted(addresses, key=lambda a: (a.version, a))


def names_for_cert():
    """(DNS names, IP addresses) the bot's certificate names."""
    host = socket.gethostname().split(".", 1)[0] or "localhost"
    names = [host, f"{host}.local", "localhost"]
    return list(dict.fromkeys(names)), [ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1"),
                                        *own_addresses()]


def make_certificate(folder, now=None):
    """Make cert.pem and key.pem in folder (readable only by this account),
    replacing any there. Returns the certificate's path."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    folder = Path(folder)
    folder.mkdir(mode=0o700, exist_ok=True)
    folder.chmod(0o700)
    names, addresses = names_for_cert()
    now = now or datetime.datetime.now(datetime.UTC)
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0]),
                         x509.NameAttribute(NameOID.ORGANIZATION_NAME, "mesh-contingency")])
    cert = (x509.CertificateBuilder()
            .subject_name(subject).issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=VALID_DAYS))
            .add_extension(x509.SubjectAlternativeName([*(x509.DNSName(n) for n in names),
                                                        *(x509.IPAddress(a) for a in addresses)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    _write_private(folder / KEY_FILE, key.private_bytes(serialization.Encoding.PEM,
                                                        serialization.PrivateFormat.PKCS8,
                                                        serialization.NoEncryption()))
    _write_private(folder / CERT_FILE, cert.public_bytes(serialization.Encoding.PEM))
    return folder / CERT_FILE


def _write_private(path, data):
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "wb") as f:
        f.write(data)
    os.replace(temp, path)


def fingerprint(cert_path):
    """The certificate's SHA-256 fingerprint, as browsers show it (AB:CD:...)."""
    try:
        pem = Path(cert_path).read_text(encoding="ascii")
        der = ssl.PEM_cert_to_DER_cert(pem)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        raise CertificateError(f"can't read the certificate {cert_path}: {getattr(e, 'strerror', None) or e}") \
            from None
    return ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())


def certificate_files(settings, config_folder):
    """(cert, key) paths to use: your own from [console], or the bot's,
    made now if there are none yet. Raises CertificateError."""
    if settings.cert:
        cert, key = Path(settings.cert).expanduser(), Path(settings.key).expanduser()
        for path in (cert, key):
            if not path.is_file():
                raise CertificateError(f"no file {path} ([console] {'cert' if path == cert else 'key'})")
        return cert, key
    folder = tls_folder(config_folder)
    cert, key = folder / CERT_FILE, folder / KEY_FILE
    if not (cert.is_file() and key.is_file()):
        if cryptography_missing():
            raise CertificateError('making its certificate needs cryptography: pip install -e ".[console]"')
        make_certificate(folder)
    return cert, key


def ssl_context(cert, key):
    """A server SSLContext for cert and key: TLS 1.2 or newer."""
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(cert, key)
    except (OSError, ssl.SSLError) as e:
        raise CertificateError(f"can't use the certificate {cert} with key {key}: {e}") from None
    return context
