"""PORT ADDITION: read single files out of a zip on a web server, without
downloading the zip.

A release is one zip of about 145 MB, and between two builds most of it - the
libraries in ``_internal`` - is the same.  A zip keeps its index at the end:
the central directory lists every member with its CRC-32, its size and where
its data starts.  GitHub serves release assets with ``Accept-Ranges: bytes``,
so the index can be fetched on its own, and then only the members whose CRC-32
differs from the file already installed.

Nothing here is specific to the game and nothing is cached: a view of a
remote archive.  Zip64 archives are refused, so the caller falls back to
downloading the whole file; the port's releases are far below its limits.
"""

from __future__ import annotations

import struct
import urllib.error
import urllib.request
import zlib

USER_AGENT = 'PapaSangreII-Updater'
TIMEOUT = 30

END_OF_CENTRAL_DIRECTORY = b'PK\x05\x06'
CENTRAL_FILE_HEADER = b'PK\x01\x02'
LOCAL_FILE_HEADER = b'PK\x03\x04'
ZIP64_END_LOCATOR = b'PK\x06\x07'

#: the end record is 22 bytes plus a comment of up to 65,535
TAIL = 65536 + 22
STORED, DEFLATED = 0, 8
#: a big member is fetched in pieces this size, so progress and a cancel keep moving
PIECE = 4 << 20


class RemoteZipError(Exception):
    """The archive cannot be read a piece at a time; download the whole thing instead."""


class Entry:
    __slots__ = ('name', 'crc', 'compressed_size', 'size', 'method', 'header_offset')

    def __init__(self, name, crc, compressed_size, size, method, header_offset):
        self.name = name
        self.crc = crc
        self.compressed_size = compressed_size
        self.size = size
        self.method = method
        self.header_offset = header_offset

    @property
    def is_dir(self) -> bool:
        return self.name.endswith('/')

    def __repr__(self) -> str:
        return '<Entry %s %d bytes crc %08x>' % (self.name, self.size, self.crc)


def _request(url: str, headers: dict):
    head = {'User-Agent': USER_AGENT}
    head.update(headers)
    return urllib.request.Request(url, headers=head)


def get_range(url: str, start: int, length: int) -> bytes:
    """The bytes [start, start+length).  A server that ignores the range and
    sends the whole file is an error, not a slow success."""
    if length <= 0:
        return b''
    end = start + length - 1
    try:
        with urllib.request.urlopen(_request(url, {'Range': 'bytes=%d-%d' % (start, end)}),
                                    timeout=TIMEOUT) as response:
            if response.status != 206:
                raise RemoteZipError('the server sent the whole file instead of a range')
            data = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 416:
            raise RemoteZipError('asked for bytes the file does not have') from exc
        raise
    if len(data) != length:
        raise RemoteZipError('the server sent %d bytes, not %d' % (len(data), length))
    return data


def content_length(url: str) -> int:
    """How big the file is, from a one-byte range (no HEAD through the redirect)."""
    with urllib.request.urlopen(_request(url, {'Range': 'bytes=0-0'}), timeout=TIMEOUT) as response:
        if response.status == 206:
            total = response.headers.get('Content-Range', '').rsplit('/', 1)[-1]
            if total.isdigit():
                return int(total)
    raise RemoteZipError('the server did not say how big the file is')


class RemoteZip:
    """The central directory of a zip on a web server, and a way to pull one member out."""

    def __init__(self, url: str, size: int | None = None):
        self.url = url
        self.size = content_length(url) if not size else int(size)
        self.entries = self._read_central_directory()

    def _read_central_directory(self) -> dict:
        tail_length = min(TAIL, self.size)
        tail = get_range(self.url, self.size - tail_length, tail_length)
        at = tail.rfind(END_OF_CENTRAL_DIRECTORY)
        if at < 0:
            raise RemoteZipError('no end-of-central-directory record: not a zip, or a zip64 one')
        entry_count, directory_size, directory_offset = struct.unpack('<HII', tail[at + 10:at + 20])
        if 0xFFFFFFFF in (directory_size, directory_offset) or entry_count == 0xFFFF \
                or tail.rfind(ZIP64_END_LOCATOR) >= 0:
            raise RemoteZipError('zip64 archives are not read a piece at a time')
        directory = get_range(self.url, directory_offset, directory_size)
        return self._parse_central_directory(directory, entry_count)

    @staticmethod
    def _parse_central_directory(directory: bytes, entry_count: int) -> dict:
        entries, at = {}, 0
        for _ in range(entry_count):
            if directory[at:at + 4] != CENTRAL_FILE_HEADER:
                raise RemoteZipError('the central directory is not laid out as expected')
            (method, crc, compressed_size, size, name_length, extra_length, comment_length,
             _attributes, header_offset) = struct.unpack('<H4xIIIHHH4xII', directory[at + 10:at + 46])
            name = directory[at + 46:at + 46 + name_length]
            try:
                name = name.decode('utf-8')
            except UnicodeDecodeError:
                name = name.decode('cp437')
            name = name.replace('\\', '/')
            entries[name] = Entry(name, crc, compressed_size, size, method, header_offset)
            at += 46 + name_length + extra_length + comment_length
        return entries

    def files(self) -> dict:
        return {name: e for name, e in self.entries.items() if not e.is_dir}

    def read_into(self, entry, out, progress=None, cancelled=None) -> None:
        """Fetch one member, decompress it into the open file ``out``, check its
        CRC-32 and size.  ``progress(n)`` is told each piece's compressed bytes."""
        if isinstance(entry, str):
            entry = self.entries[entry]
        if entry.is_dir:
            return
        header = get_range(self.url, entry.header_offset, 30)
        if header[:4] != LOCAL_FILE_HEADER:
            raise RemoteZipError('%s does not start with a local file header' % entry.name)
        name_length, extra_length = struct.unpack('<HH', header[26:30])
        start = entry.header_offset + 30 + name_length + extra_length
        if entry.method == DEFLATED:
            inflate = zlib.decompressobj(-zlib.MAX_WBITS)
        elif entry.method != STORED:
            raise RemoteZipError('%s uses compression method %d' % (entry.name, entry.method))
        crc, size, done = 0, 0, 0
        while done < entry.compressed_size:
            if cancelled is not None and cancelled():
                raise RemoteZipError('cancelled')
            n = min(PIECE, entry.compressed_size - done)
            raw = get_range(self.url, start + done, n)
            done += n
            data = inflate.decompress(raw) if entry.method == DEFLATED else raw
            crc = zlib.crc32(data, crc)
            size += len(data)
            out.write(data)
            if progress is not None:
                progress(n)
        if entry.method == DEFLATED:
            data = inflate.flush()
            crc = zlib.crc32(data, crc)
            size += len(data)
            out.write(data)
        if size != entry.size:
            raise RemoteZipError('%s unpacked to %d bytes, not %d' % (entry.name, size, entry.size))
        if crc != entry.crc:
            raise RemoteZipError('%s did not survive the download intact' % entry.name)
