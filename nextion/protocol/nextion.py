import binascii
import logging
import typing
from enum import IntEnum

from .base import BasicProtocol

logger = logging.getLogger("nextion").getChild(__name__)


class EventType(IntEnum):
    TOUCH = 0x65  # Touch event
    TOUCH_COORDINATE = 0x67  # Touch coordinate
    TOUCH_IN_SLEEP = 0x68  # Touch event in sleep mode
    AUTO_SLEEP = 0x86  # Device automatically enters into sleep mode
    AUTO_WAKE = 0x87  # Device automatically wake up
    STARTUP = 0x88  # System successful start up
    SD_CARD_UPGRADE = 0x89  # Start SD card upgrade


class ResponseType(IntEnum):
    STRING = 0x70
    NUMBER = 0x71
    PAGE = 0x66


class NextionProtocol(BasicProtocol):
    EOL = b"\xff\xff\xff"

    PACKET_LENGTH_MAP = {
        0x00: 6,  # Nextion Startup
        0x24: 4,  # Serial Buffer Overflow
        0x65: 7,  # Touch Event
        0x66: 5,  # Current Page Number
        0x67: 9,  # Touch Coordinate(awake)
        0x68: 9,  # Touch Coordinate(sleep)
        0x71: 8,  # Numeric Data Enclosed
        0x86: 4,  # Auto Entered Sleep Mode
        0x87: 4,  # Auto Wake from Sleep
        0x88: 4,  # Nextion Ready
        0x89: 4,  # Start microSD Upgrade
        0xFD: 4,  # Transparent Data Finished
        0xFE: 4,  # Transparent Data Ready
    }

    def __init__(self, event_message_handler: typing.Callable):
        super(NextionProtocol, self).__init__()
        self.buffer = b""
        self.dropped_buffer = b""
        self.event_message_handler = event_message_handler

    def is_event(self, message):
        return len(message) > 0 and message[0] in EventType.__members__.values()

    def data_received(self, data):
        self.buffer += data

        while True:
            message = self._extract_packet()

            if message is None:  # EOL not found
                break

            self._reset_dropped_buffer()
            logger.debug("received: %s", binascii.hexlify(message))

            if self.is_event(message):
                self.event_message_handler(message)
            else:
                self.queue.put_nowait(message)

    def _reset_dropped_buffer(self):
        if len(self.dropped_buffer):
            logger.warning(
                "Junk received. Dropped bytes %s", binascii.hexlify(self.dropped_buffer)
            )
            self.dropped_buffer = b""

    def _extract_packet(self):
        if len(self.buffer) < 3:
            return None

        expected_packet_length = self.PACKET_LENGTH_MAP.get(self.buffer[0])
        if expected_packet_length is None:
            return self._extract_varied_length_packet()
        else:
            return self._extract_fixed_length_packet(expected_packet_length)

    def _extract_fixed_length_packet(self, expected_packet_length):
        buffer_len = len(self.buffer)
        if buffer_len < expected_packet_length:
            return None

        full_message = self.buffer[:expected_packet_length]
        if not full_message.endswith(self.EOL):
            message = self._extract_varied_length_packet()
            if message is None:
                return None

            self.dropped_buffer += message + self.EOL
            return self._extract_packet()
        self.buffer = self.buffer[expected_packet_length:]
        return full_message[:-3]

    def _extract_varied_length_packet(self):
        message, eol, leftover = self.buffer.partition(self.EOL)
        if eol == b"":
            return None

        self.buffer = leftover
        return message

    def write(self, data: bytes, eol=True):
        assert isinstance(data, bytes)
        self.transport.write(data + self.EOL if eol else b"")
        logger.debug("sent: %s", data)
