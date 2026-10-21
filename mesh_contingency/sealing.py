"""Sealing mailbox messages to a passphrase, so mailbox.json can't be read.

A passphrase is turned into an X25519 key pair (scrypt, then X25519). Only
the public half is kept, in the user's section of the users file:

    inbox_key = { public = "<64 hex>", salt = "<32 hex>", n = 65536 }

Sealing needs only that public half: each message gets a throwaway key pair,
whose private half is combined with it into a one-off AES-GCM key and then
forgotten. Opening needs the passphrase, which gives back the private half
and so the same AES key. Neither the passphrase nor any private key is kept.
"""

import base64
import hmac
import os

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.DH import import_x25519_private_key, import_x25519_public_key, key_agreement
from Crypto.Protocol.KDF import HKDF, scrypt
from Crypto.PublicKey import ECC

MIN_LENGTH = 12
MAX_LENGTH = 16
# scrypt cost: 2**16 takes 64 MB and a fraction of a second, so guessing a
# passphrase from a copied mailbox.json is slow. Kept with each key, so it can
# be raised later without breaking existing ones.
SCRYPT_N = 2**16
SALT_BYTES = 16


class SealError(Exception):
    """A sealed message or inbox key that can't be used."""


def check_passphrase(passphrase):
    """Return why a passphrase can't be used, or None if it can."""
    if not MIN_LENGTH <= len(passphrase) <= MAX_LENGTH:
        return f"must be {MIN_LENGTH} to {MAX_LENGTH} characters"
    if any(ch.isspace() for ch in passphrase):
        return "can't contain spaces"
    if not passphrase.isprintable():
        return "can't contain control characters"
    return None


def _raw_public(key):
    return key.public_key().export_key(format="raw")


def _private_key(passphrase, inbox_key):
    salt = bytes.fromhex(inbox_key["salt"])
    seed = scrypt(passphrase.encode("utf-8"), salt, 32, N=inbox_key["n"], r=8, p=1)
    return import_x25519_private_key(seed)


def new_inbox_key(passphrase):
    """Return the inbox_key setting for a new passphrase. Slow (scrypt)."""
    inbox_key = {"salt": os.urandom(SALT_BYTES).hex(), "n": SCRYPT_N}
    return {"public": _raw_public(_private_key(passphrase, inbox_key)).hex(), **inbox_key}


def unlock(passphrase, inbox_key):
    """Return the private key for inbox_key, or None if the passphrase is
    wrong. Slow (scrypt)."""
    try:
        private = _private_key(passphrase, inbox_key)
        expected = bytes.fromhex(inbox_key["public"])
    except (KeyError, TypeError, ValueError) as e:
        raise SealError(f"bad inbox_key: {e}") from None
    return private if hmac.compare_digest(_raw_public(private), expected) else None


def _aes_key(shared, ephemeral_public, recipient_public):
    # Both public halves go into the key, so a sealed message can't be
    # passed off as sealed to another key.
    return HKDF(shared, 32, ephemeral_public + recipient_public, SHA256, context=b"mesh-contingency inbox")


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def seal(text, inbox_key):
    """Return text sealed to inbox_key, as {"epk", "nonce", "ct"} (base64)."""
    try:
        recipient_public = bytes.fromhex(inbox_key["public"])
        recipient = import_x25519_public_key(recipient_public)
    except (KeyError, TypeError, ValueError) as e:
        raise SealError(f"bad inbox_key: {e}") from None
    ephemeral = ECC.generate(curve="curve25519")
    ephemeral_public = _raw_public(ephemeral)
    key = key_agreement(static_priv=ephemeral, static_pub=recipient,
                        kdf=lambda shared: _aes_key(shared, ephemeral_public, recipient_public))
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(text.encode("utf-8"))
    return {"epk": _b64(ephemeral_public), "nonce": _b64(cipher.nonce), "ct": _b64(ciphertext + tag)}


def open_sealed(sealed, private):
    """Return the text of a sealed message, given the private key from
    unlock(). Raises SealError if it wasn't sealed to that key or was changed."""
    try:
        ephemeral_public = base64.b64decode(sealed["epk"], validate=True)
        nonce = base64.b64decode(sealed["nonce"], validate=True)
        data = base64.b64decode(sealed["ct"], validate=True)
        key = key_agreement(static_priv=private, static_pub=import_x25519_public_key(ephemeral_public),
                            kdf=lambda shared: _aes_key(shared, ephemeral_public, _raw_public(private)))
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(data[:-16], data[-16:]).decode("utf-8")
    except (KeyError, TypeError, ValueError) as e:
        raise SealError(f"can't be opened: {e}") from None
