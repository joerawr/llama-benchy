"""Read a GGUF metadata field without dependencies or loading tensor weights."""
import struct
from pathlib import Path


def read_field(path: Path, wanted: str):
    formats = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
    with path.open("rb") as handle:
        def number(fmt):
            return struct.unpack("<" + fmt, handle.read(struct.calcsize(fmt)))[0]

        def value(kind, read=False):
            if kind == 8:
                size = number("Q")
                if read:
                    return handle.read(size).decode("utf-8")
                handle.seek(size, 1)
                return None
            if kind == 9:
                element, size = number("I"), number("Q")
                if read:
                    return [value(element, True) for _ in range(size)]
                if element in formats:
                    handle.seek(struct.calcsize(formats[element]) * size, 1)
                else:
                    for _ in range(size):
                        value(element)
                return None
            if kind not in formats:
                raise ValueError(f"Unknown GGUF metadata type {kind}")
            return number(formats[kind])

        if handle.read(4) != b"GGUF" or number("I") not in (2, 3):
            raise ValueError("Expected a little-endian GGUF v2/v3 model")
        number("Q")  # tensor count
        fields = number("Q")
        for _ in range(fields):
            key, kind = value(8, True), number("I")
            if key == wanted:
                return value(kind, True)
            value(kind)
    raise KeyError(f"GGUF metadata field absent: {wanted}")
