"""
MS2Extra Serial Protocol implementation.

Implements the newserial protocol used by TunerStudio to communicate with
Megasquirt ECUs. Supports both simple and CAN-style commands.

Protocol format (newserial):
- Request: [size:2][payload][crc32:4]
- Response: [size:2][flag:1][payload][crc32:4]

Commands:
- 'Q' - Query signature
- 'A' - Get all realtime data (OUTPC)
- 'F' - Protocol version (unframed, returns "002")
- 'r' - CAN-style read: r + canId + table + offset(2) + count(2)
- 'w' - CAN-style write
- 'S' - Get version info
"""

from __future__ import annotations
import binascii
import struct
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class ProtocolConfig:
    """Protocol configuration."""

    signature: str = "MS2Extra comms330NP"
    protocol_version: str = "002"
    can_id: int = 0
    och_block_size: int = 209


class SerialProtocol:
    """MS2Extra serial protocol handler."""

    # Table IDs for CAN-style commands
    TABLE_OUTPC = 0x07  # Realtime data
    TABLE_SIGNATURE = 0x0F  # ECU signature
    TABLE_VERSION = 0x0E  # Version info

    # Flash pages (configuration data)
    TABLE_PAGE_0 = 0x04
    TABLE_PAGE_1 = 0x05
    TABLE_PAGE_2 = 0x06
    TABLE_PAGE_3 = 0x08
    TABLE_PAGE_4 = 0x09
    TABLE_PAGE_5 = 0x0A
    TABLE_PAGE_6 = 0x0B
    TABLE_PAGE_7 = 0x0C
    TABLE_PAGE_8 = 0x0D

    # Response flags
    FLAG_OK = 0x00
    FLAG_REALTIME = 0x01
    FLAG_ERROR_UNRECOGNIZED = 0x83

    def __init__(self, config: Optional[ProtocolConfig] = None):
        self.config = config or ProtocolConfig()
        self._outpc_builder: Optional[Callable[[], bytes]] = None
        self._page_data: dict[int, bytes] = {}
        self._pages_modified: bool = False

    def set_outpc_builder(self, builder: Callable[[], bytes]):
        """Set the function that builds OUTPC data."""
        self._outpc_builder = builder

    def set_page_data(self, table_id: int, data: bytes):
        """Set configuration page data."""
        self._page_data[table_id] = bytearray(data)

    def get_page_data(self, table_id: int) -> bytes:
        """Get configuration page data."""
        return bytes(self._page_data.get(table_id, b""))

    def get_all_page_data(self) -> dict[int, bytes]:
        """Get all page data as immutable bytes."""
        return {k: bytes(v) for k, v in self._page_data.items()}

    def is_pages_modified(self) -> bool:
        """Check if pages have been modified by writes."""
        return self._pages_modified

    def clear_pages_modified(self):
        """Clear the pages modified flag."""
        self._pages_modified = False

    @staticmethod
    def crc32(data: bytes) -> int:
        """Calculate CRC32 as used by Megasquirt."""
        return binascii.crc32(data) & 0xFFFFFFFF

    def build_response(self, flag: int, payload: bytes) -> bytes:
        """Build a newserial response packet."""
        data = bytes([flag]) + payload
        crc = self.crc32(data)
        return struct.pack(">H", len(data)) + data + struct.pack(">I", crc)

    def parse_framed_request(self, buffer: bytes) -> tuple[Optional[bytes], bytes]:
        """
        Parse a newserial framed request from buffer.

        Returns:
            Tuple of (payload or None, remaining buffer bytes)
        """
        if len(buffer) < 2:
            return None, buffer

        size = struct.unpack(">H", buffer[:2])[0]

        # Sanity check
        if size == 0 or size > 1024:
            # Invalid size, skip this byte
            return None, buffer[1:]

        # Need size + 2 (header) + 4 (crc) bytes total
        total_needed = 2 + size + 4

        if len(buffer) < total_needed:
            return None, buffer

        # Extract and verify
        payload = buffer[2 : 2 + size]
        crc_bytes = buffer[2 + size : 2 + size + 4]
        remaining = buffer[total_needed:]

        crc_rx = struct.unpack(">I", crc_bytes)[0]
        if crc_rx != self.crc32(payload):
            return None, remaining

        return payload, remaining

    def handle_request(self, request: bytes) -> Optional[bytes]:
        """
        Handle a protocol request and return response.

        Args:
            request: The payload bytes (without framing)

        Returns:
            Response bytes (with framing) or None
        """
        if not request:
            return None

        cmd = request[0:1]

        # Simple signature query
        if cmd == b"Q":
            return self._handle_signature_query()

        # Simple realtime data request
        if cmd == b"A":
            return self._handle_realtime_query()

        # Version info
        if cmd == b"S":
            return self._handle_version_query()

        # CAN-style read command
        if cmd == b"r" and len(request) >= 7:
            return self._handle_can_read(request)

        # CAN-style write command
        if cmd == b"w" and len(request) >= 7:
            return self._handle_can_write(request)

        # CRC check command (used by TunerStudio to verify page data)
        if cmd == b"k" and len(request) >= 7:
            return self._handle_crc_check(request)

        # Burn command (saves RAM to flash) - just acknowledge
        if cmd == b"b" and len(request) >= 3:
            return self._handle_burn(request)

        # Unknown command
        return self.build_response(self.FLAG_ERROR_UNRECOGNIZED, b"")

    def _handle_signature_query(self) -> bytes:
        """Handle 'Q' command - signature query."""
        sig_bytes = self.config.signature.encode("utf-8") + b"\x00"
        return self.build_response(self.FLAG_OK, sig_bytes)

    def _handle_realtime_query(self) -> bytes:
        """Handle 'A' command - realtime data query."""
        if self._outpc_builder:
            outpc = self._outpc_builder()
        else:
            outpc = bytes(self.config.och_block_size)
        return self.build_response(self.FLAG_REALTIME, outpc)

    def _handle_version_query(self) -> bytes:
        """Handle 'S' command - version info."""
        version = self.config.signature.encode("utf-8") + b"\x00"
        return self.build_response(self.FLAG_OK, version)

    def _handle_can_read(self, request: bytes) -> bytes:
        """
        Handle CAN-style read command.

        Format: r + canId(1) + table(1) + offset(2) + count(2)
        """
        # Parse request
        # can_id = request[1]  # Not used in simulator
        table = request[2]
        offset = struct.unpack(">H", request[3:5])[0]
        count = struct.unpack(">H", request[5:7])[0]

        if table == self.TABLE_SIGNATURE:
            # Signature query
            sig_data = (self.config.signature.encode("utf-8") + b"\x00").ljust(
                20, b"\x00"
            )
            return self.build_response(self.FLAG_OK, sig_data[offset : offset + count])

        elif table == self.TABLE_VERSION:
            # Version info
            ver_data = (self.config.signature.encode("utf-8") + b"\x00").ljust(
                60, b"\x00"
            )
            return self.build_response(self.FLAG_OK, ver_data[offset : offset + count])

        elif table == self.TABLE_OUTPC:
            # Realtime data
            if self._outpc_builder:
                outpc = self._outpc_builder()
            else:
                outpc = bytes(self.config.och_block_size)
            return self.build_response(
                self.FLAG_REALTIME, outpc[offset : offset + count]
            )

        elif table in self._page_data:
            # Configuration page
            page_data = self._page_data[table]
            return self.build_response(self.FLAG_OK, page_data[offset : offset + count])

        elif table in (
            self.TABLE_PAGE_0,
            self.TABLE_PAGE_1,
            self.TABLE_PAGE_2,
            self.TABLE_PAGE_3,
            self.TABLE_PAGE_4,
            self.TABLE_PAGE_5,
            self.TABLE_PAGE_6,
            self.TABLE_PAGE_7,
            self.TABLE_PAGE_8,
        ):
            # Unknown page - return zeros
            return self.build_response(self.FLAG_OK, bytes(count))

        else:
            # Unknown table - return zeros
            return self.build_response(self.FLAG_OK, bytes(count))

    def _handle_can_write(self, request: bytes) -> bytes:
        """
        Handle CAN-style write command.

        Format: w + canId(1) + table(1) + offset(2) + count(2) + data

        Stores the data into page buffers for persistence.
        """
        if len(request) < 7:
            return self.build_response(self.FLAG_OK, b"")

        # Parse request
        table = request[2]
        offset = struct.unpack(">H", request[3:5])[0]
        count = struct.unpack(">H", request[5:7])[0]
        data = request[7:7 + count]

        # Store into page buffer if it exists
        if table in self._page_data:
            page_data = self._page_data[table]
            # Ensure we have a mutable buffer
            if not isinstance(page_data, bytearray):
                page_data = bytearray(page_data)
                self._page_data[table] = page_data
            # Write the data
            end_offset = offset + len(data)
            if end_offset <= len(page_data):
                page_data[offset:end_offset] = data
                self._pages_modified = True
        else:
            # Create new page buffer (1024 bytes default)
            page_data = bytearray(1024)
            end_offset = offset + len(data)
            if end_offset <= len(page_data):
                page_data[offset:end_offset] = data
            self._page_data[table] = page_data
            self._pages_modified = True

        return self.build_response(self.FLAG_OK, b"")

    def _handle_crc_check(self, request: bytes) -> bytes:
        """
        Handle CRC check command.

        Format: k + canId(1) + table(1) + offset(2) + count(2)

        Returns CRC32 of the requested page data range.
        """
        # Parse request
        table = request[2]
        offset = struct.unpack(">H", request[3:5])[0]
        count = struct.unpack(">H", request[5:7])[0]

        # Get the page data
        if table in self._page_data:
            page_data = self._page_data[table]
            data_slice = page_data[offset:offset + count]
        else:
            # Return CRC of zeros for unknown pages
            data_slice = bytes(count)

        # Calculate and return CRC32
        crc = self.crc32(data_slice)
        return self.build_response(self.FLAG_OK, struct.pack(">I", crc))

    def _handle_burn(self, request: bytes) -> bytes:
        """
        Handle burn command (save RAM to flash).

        Format: b + canId(1) + table(1)

        For simulator, just acknowledge - no actual flash to save.
        """
        # In a real ECU this would save RAM page to flash
        # For simulator, just acknowledge success
        return self.build_response(self.FLAG_OK, b"")


class RequestBuffer:
    """Buffer for accumulating and parsing serial requests."""

    def __init__(self, protocol: SerialProtocol):
        self.protocol = protocol
        self.buffer = b""

    def add_data(self, data: bytes):
        """Add received data to buffer."""
        self.buffer += data

    def get_next_response(self) -> Optional[bytes]:
        """
        Try to parse and handle the next request from buffer.

        Returns:
            Response bytes or None if no complete request available.
        """
        if not self.buffer:
            return None

        # Check for unframed 'F' command (protocol version query)
        if self.buffer[0:1] == b"F":
            self.buffer = self.buffer[1:]
            return self.protocol.config.protocol_version.encode("utf-8")

        # Try to parse framed request
        request, self.buffer = self.protocol.parse_framed_request(self.buffer)
        if request is not None:
            return self.protocol.handle_request(request)

        return None

    def clear(self):
        """Clear the buffer."""
        self.buffer = b""
