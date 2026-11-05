import gzip
import html.entities
import io
import re
from pathlib import Path
from typing import BinaryIO

_ENTITY_PATTERN = re.compile(rb"&([A-Za-z][A-Za-z0-9]+);")
_XML_ENTITIES = {b"amp", b"lt", b"gt", b"quot", b"apos"}


def _replace_entity(match: re.Match[bytes]) -> bytes:
    name = match.group(1)
    if name in _XML_ENTITIES:
        return match.group(0)
    codepoint = html.entities.name2codepoint.get(name.decode("ascii"))
    if codepoint is None:
        return match.group(0)
    return f"&#{codepoint};".encode("ascii")


class EntityNormalizingReader(io.RawIOBase):
    """Normalize DBLP's HTML named entities without buffering the whole dump."""

    def __init__(self, source: BinaryIO, chunk_size: int = 1024 * 1024):
        self._source = source
        self._chunk_size = chunk_size
        self._pending = b""
        self._output = b""
        self._finished = False

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        try:
            self._source.close()
        finally:
            super().close()

    def readinto(self, buffer: bytearray) -> int:
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        while not self._finished and (size < 0 or len(self._output) < size):
            chunk = self._source.read(self._chunk_size)
            if not chunk:
                self._output += _ENTITY_PATTERN.sub(_replace_entity, self._pending)
                self._pending = b""
                self._finished = True
                break
            data = self._pending + chunk
            last_ampersand = data.rfind(b"&")
            last_semicolon = data.rfind(b";")
            if last_ampersand > last_semicolon:
                self._pending = data[last_ampersand:]
                data = data[:last_ampersand]
            else:
                self._pending = b""
            self._output += _ENTITY_PATTERN.sub(_replace_entity, data)
        if size < 0:
            result, self._output = self._output, b""
            return result
        result, self._output = self._output[:size], self._output[size:]
        return result


def open_xml_stream(path: str | Path) -> io.BufferedReader:
    file_path = Path(path)
    source: BinaryIO
    if file_path.suffix == ".gz":
        source = gzip.open(file_path, "rb")
    else:
        source = file_path.open("rb")
    return io.BufferedReader(EntityNormalizingReader(source))
