import struct


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def mp4_with_comment(text: str) -> bytes:
    data = box(b"data", struct.pack(">II", 1, 0) + text.encode("utf-8"))
    ilst = box(b"ilst", box(b"\xa9cmt", data))
    meta = box(b"meta", b"\x00\x00\x00\x00" + box(b"hdlr", b"\x00" * 25) + ilst)
    moov = box(b"moov", box(b"mvhd", b"\x00" * 100) + box(b"udta", meta))
    return box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41") + moov
