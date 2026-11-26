"""Minimal, dependency-free IMG4/IM4P reader (DER) — enough to identify and unwrap payloads.

Supports reading the IM4P fourcc, description, payload and the optional compression
info. Decryption is intentionally out of scope: Halcyon only handles payloads that are
unencrypted in the public IPSW (kernelcache, DeviceTree on A10 are not encrypted).
"""

from __future__ import annotations

from dataclasses import dataclass


class DERError(ValueError):
    pass


def _read_tlv(buf: bytes, off: int) -> tuple[int, int, int]:
    """Return (tag, value_offset, value_length)."""
    if off + 2 > len(buf):
        raise DERError("truncated TLV")
    tag = buf[off]
    off += 1
    if tag & 0x1F == 0x1F:  # high-tag-number form (used by IMG4 manifests)
        while buf[off] & 0x80:
            off += 1
        off += 1
    ln = buf[off]
    off += 1
    if ln & 0x80:
        n = ln & 0x7F
        if n == 0 or n > 4:
            raise DERError("unsupported length form")
        ln = int.from_bytes(buf[off:off + n], "big")
        off += n
    if off + ln > len(buf):
        raise DERError("TLV exceeds buffer")
    return tag, off, ln


def _children(buf: bytes, off: int, ln: int):
    end = off + ln
    while off < end:
        tag, voff, vlen = _read_tlv(buf, off)
        yield tag, voff, vlen
        off = voff + vlen


@dataclass
class IM4P:
    fourcc: str
    description: str
    payload: bytes
    compression: tuple[int, int] | None  # (algorithm, uncompressed size)
    has_keybag: bool

    @property
    def payload_kind(self) -> str:
        p = self.payload
        if p[:4] == b"bvx2" or p[:4] == b"bvx-" or p[:4] == b"bvxn":
            return "lzfse"
        if p[:8] == b"complzss":
            return "lzss"
        if p[:4] in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
            return "macho"
        return "raw"


def parse_im4p(data: bytes) -> IM4P:
    tag, off, ln = _read_tlv(data, 0)
    if tag != 0x30:
        raise DERError("not a DER SEQUENCE")
    items = list(_children(data, off, ln))
    if len(items) < 4:
        raise DERError("IM4P sequence too short")
    strs = [data[o:o + l] for t, o, l in items[:3]]
    if strs[0] == b"IMG4":
        raise DERError("full IMG4 container; extract the IM4P first")
    if strs[0] != b"IM4P":
        raise DERError(f"unexpected magic {strs[0]!r}")
    t, o, l = items[3]
    if t != 0x04:
        raise DERError("payload is not an OCTET STRING")
    payload = data[o:o + l]
    has_keybag = False
    compression = None
    for t, o, l in items[4:]:
        if t == 0x04:
            has_keybag = True
        elif t == 0x30:
            ints = [int.from_bytes(data[io:io + il], "big")
                    for it, io, il in _children(data, o, l) if it == 0x02]
            if len(ints) == 2:
                compression = (ints[0], ints[1])
    return IM4P(strs[1].decode("ascii", "replace"), strs[2].decode("utf-8", "replace"),
                payload, compression, has_keybag)


def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def build_im4p(fourcc: str, description: str, payload: bytes) -> bytes:
    """Wrap a payload into an (unsigned) IM4P. Used by tests and by the Build Engine."""
    def tlv(tag: int, v: bytes) -> bytes:
        return bytes([tag]) + _der_len(len(v)) + v
    body = tlv(0x16, b"IM4P") + tlv(0x16, fourcc.encode()) + tlv(0x16, description.encode()) + tlv(0x04, payload)
    return tlv(0x30, body)
