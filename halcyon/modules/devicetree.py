"""Apple flattened DeviceTree parser and differ.

Format (little-endian):
  node     := u32 n_props, u32 n_children, prop[n_props], node[n_children]
  prop     := char name[32], u32 length (bit31 = placeholder), u8 value[length], pad to 4
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

PLACEHOLDER = 0x80000000


@dataclass
class DTNode:
    props: dict[str, bytes] = field(default_factory=dict)
    children: list["DTNode"] = field(default_factory=list)

    @property
    def name(self) -> str:
        return _cstr(self.props.get("name", b"?"))

    def compatible(self) -> list[str]:
        raw = self.props.get("compatible", b"")
        return [s.decode("ascii", "replace") for s in raw.split(b"\0") if s]

    def walk(self, prefix: str = ""):
        path = f"{prefix}/{self.name}" if prefix else self.name
        yield path, self
        for c in self.children:
            yield from c.walk(path)


def _cstr(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("ascii", "replace")


def parse(data: bytes) -> DTNode:
    node, off = _parse_node(data, 0)
    return node


def _parse_node(data: bytes, off: int) -> tuple[DTNode, int]:
    if off + 8 > len(data):
        raise ValueError("truncated node header")
    nprops, nchildren = struct.unpack_from("<II", data, off)
    if nprops > 4096 or nchildren > 4096:
        raise ValueError("implausible node header (not an Apple DeviceTree?)")
    off += 8
    node = DTNode()
    for _ in range(nprops):
        name = _cstr(data[off:off + 32])
        (ln,) = struct.unpack_from("<I", data, off + 32)
        off += 36
        size = ln & ~PLACEHOLDER
        node.props[name] = data[off:off + size]
        off += (size + 3) & ~3
    for _ in range(nchildren):
        child, off = _parse_node(data, off)
        node.children.append(child)
    return node, off


def serialize(node: DTNode) -> bytes:
    out = bytearray(struct.pack("<II", len(node.props), len(node.children)))
    for name, val in node.props.items():
        nb = name.encode()[:31]
        out += nb + b"\0" * (32 - len(nb))
        out += struct.pack("<I", len(val)) + val + b"\0" * (-len(val) % 4)
    for c in node.children:
        out += serialize(c)
    return bytes(out)


@dataclass
class DTDiff:
    only_a: list[str]
    only_b: list[str]
    compatible_changed: list[tuple[str, list[str], list[str]]]


def diff(a: DTNode, b: DTNode) -> DTDiff:
    ma = {p: n for p, n in a.walk()}
    mb = {p: n for p, n in b.walk()}
    changed = []
    for p in sorted(ma.keys() & mb.keys()):
        ca, cb = ma[p].compatible(), mb[p].compatible()
        if ca != cb:
            changed.append((p, ca, cb))
    return DTDiff(sorted(ma.keys() - mb.keys()), sorted(mb.keys() - ma.keys()), changed)
