"""NTRIP client: connects to an NTRIP caster and exposes the data as a readable stream."""

from __future__ import annotations

import base64
import io
import socket
from typing import BinaryIO, Optional


_USER_AGENT = "NTRIP ntrip-to-serial/0.1.0"
_TIMEOUT = 15  # seconds


class NTRIPError(Exception):
    """Raised when the NTRIP connection fails or returns an error."""


class NTRIPClient:
    """Minimal NTRIP client (v1 / v2) that exposes a file-like byte stream.

    After calling :meth:`connect`, use :attr:`stream` as the *datastream*
    argument to :class:`pyrtcm.RTCMReader`.
    """

    def __init__(
        self,
        host: str,
        port: int,
        mountpoint: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        # Strip leading slash so callers can pass either "/MOUNT" or "MOUNT".
        self.mountpoint = mountpoint.lstrip("/")
        self.username = username
        self.password = password

        self._sock: Optional[socket.socket] = None
        # Buffered file-like view of the socket used during the handshake and
        # afterwards as the raw data stream.
        self._file: Optional[BinaryIO] = None
        self.stream: Optional[BinaryIO] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the TCP connection and perform the NTRIP handshake.

        On success, :attr:`stream` is ready to be read.
        Raises :exc:`NTRIPError` on failure.
        """
        self._sock = socket.create_connection((self.host, self.port), timeout=_TIMEOUT)
        self._sock.settimeout(_TIMEOUT)

        self._send_request()

        # Wrap the socket in a buffered binary file so that all header reads
        # benefit from kernel-level buffering instead of recv(1) calls.
        self._file = self._sock.makefile("rb")

        # Read status line so we can handle both ICY (v1) and HTTP (v2).
        status_line = self._file.readline().strip()
        if status_line.startswith(b"ICY"):
            self._handle_icy(status_line)
        elif status_line.upper().startswith(b"HTTP"):
            self._handle_http(status_line)
        else:
            raise NTRIPError(f"Unexpected response from server: {status_line!r}")

    def close(self) -> None:
        """Close the underlying socket."""
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self.stream = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_request(self) -> bytes:
        lines: list[str] = [
            f"GET /{self.mountpoint} HTTP/1.1",
            f"Host: {self.host}:{self.port}",
            "Ntrip-Version: Ntrip/2.0",
            f"User-Agent: {_USER_AGENT}",
            "Accept: */*",
            "Connection: close",
        ]
        if self.username is not None:
            raw = f"{self.username}:{self.password or ''}".encode()
            encoded = base64.b64encode(raw).decode()
            lines.append(f"Authorization: Basic {encoded}")
        lines += ["", ""]
        return "\r\n".join(lines).encode()

    def _send_request(self) -> None:
        assert self._sock is not None
        self._sock.sendall(self._build_request())

    def _read_headers(self) -> dict[str, str]:
        """Read HTTP headers after the status line; return a lower-cased dict."""
        assert self._file is not None
        headers: dict[str, str] = {}
        for line in self._file:
            stripped = line.strip()
            if not stripped:
                break
            if b":" in stripped:
                key, _, value = stripped.partition(b":")
                headers[key.strip().lower().decode()] = value.strip().decode()
        return headers

    def _handle_icy(self, status_line: bytes) -> None:
        """NTRIPv1 "ICY 200 OK" response — raw stream follows the headers."""
        parts = status_line.split()
        if len(parts) < 2 or parts[1] != b"200":
            code = parts[1].decode() if len(parts) >= 2 else "?"
            raise NTRIPError(f"NTRIP server returned ICY status {code}")
        self._read_headers()  # discard headers
        self.stream = self._file

    def _handle_http(self, status_line: bytes) -> None:
        """HTTP/1.x response — may be chunked (NTRIPv2) or plain."""
        parts = status_line.split()
        if len(parts) < 2:
            raise NTRIPError(f"Malformed HTTP status line: {status_line!r}")
        code = int(parts[1])
        if code != 200:
            raise NTRIPError(f"NTRIP server returned HTTP {code}")
        headers = self._read_headers()
        if "chunked" in headers.get("transfer-encoding", "").lower():
            self.stream = _ChunkedStream(self._file)
        else:
            self.stream = self._file


# ---------------------------------------------------------------------------
# Chunked transfer-encoding decoder
# ---------------------------------------------------------------------------


class _ChunkedStream(io.RawIOBase):
    """Decode HTTP chunked transfer-encoding from a buffered binary file.

    Wraps the socket's :meth:`makefile` object so all reads are already
    buffered; chunk-size lines are read with :meth:`readline` rather than
    byte-by-byte.
    """

    def __init__(self, fp: BinaryIO) -> None:
        self._fp = fp
        self._buf = bytearray()
        self._eof = False

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        if size == -1:
            chunks: list[bytes] = []
            while True:
                chunk = self._read_chunk()
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        while len(self._buf) < size and not self._eof:
            chunk = self._read_chunk()
            if chunk:
                self._buf.extend(chunk)
            else:
                break
        data = bytes(self._buf[:size])
        del self._buf[:size]
        return data

    def readinto(self, b: bytearray) -> int:
        data = self.read(len(b))
        n = len(data)
        b[:n] = data
        return n

    def _read_chunk(self) -> bytes:
        if self._eof:
            return b""
        size_line = self._fp.readline().strip()
        if not size_line:
            return b""
        chunk_size = int(size_line.split(b";")[0], 16)
        if chunk_size == 0:
            self._eof = True
            return b""
        data = self._fp.read(chunk_size)
        self._fp.readline()  # consume trailing CRLF
        return data
