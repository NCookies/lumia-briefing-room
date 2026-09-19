"""일회성 조사 도구: Steam의 gamerecording.pb / clip.pb를
스키마 없이 protobuf wire format으로만 훑는다.

usage: decode_pb.py <file> [max_records]
"""
import sys, datetime as dt

buf = open(sys.argv[1], "rb").read()
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 6

def varint(b, i):
    r = s = 0
    while True:
        x = b[i]; i += 1
        r |= (x & 0x7F) << s
        if not x & 0x80:
            return r, i
        s += 7

def walk(b, depth=0, budget=[400]):
    i = 0
    while i < len(b) and budget[0] > 0:
        try:
            key, i = varint(b, i)
        except IndexError:
            return
        f, wt = key >> 3, key & 7
        pad = "  " * depth
        if wt == 0:
            v, i = varint(b, i)
            hint = ""
            if 1_000_000_000 < v < 4_000_000_000:
                hint = f"  <- {dt.datetime.fromtimestamp(v)} (epoch초?)"
            elif 1_000_000_000_000 < v < 4_000_000_000_000:
                hint = f"  <- {dt.datetime.fromtimestamp(v/1000)} (epoch밀리초?)"
            budget[0] -= 1
            print(f"{pad}f{f} varint = {v}{hint}")
        elif wt == 2:
            n, i = varint(b, i)
            sub = b[i:i + n]; i += n
            budget[0] -= 1
            try:
                s = sub.decode("utf-8")
                if s.isprintable():
                    print(f"{pad}f{f} str = {s!r}")
                    continue
            except UnicodeDecodeError:
                pass
            print(f"{pad}f{f} msg ({n} bytes):")
            walk(sub, depth + 1, budget)
        elif wt == 5:
            i += 4; budget[0] -= 1; print(f"{pad}f{f} fixed32")
        elif wt == 1:
            i += 8; budget[0] -= 1; print(f"{pad}f{f} fixed64")
        else:
            print(f"{pad}f{f} wt={wt} (알 수 없음, 중단)")
            return

print(f"== {sys.argv[1]} ({len(buf)} bytes) ==")
walk(buf)
