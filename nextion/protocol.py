import asyncio
import binascii
import logging
import typing
from enum import IntEnum

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


class NextionProtocol(asyncio.Protocol):
    EOL = b"\xff\xff\xff"

    def __init__(self, event_message_handler: typing.Callable):
        self.transport = None
        self.buffer = b""
        self.queue = asyncio.Queue()
        self.connect_future = asyncio.get_event_loop().create_future()
        self.disconnect_future = asyncio.get_event_loop().create_future()
        self.event_message_handler = event_message_handler
        self._upload_mode = False

    def start_upload(self):
        self._upload_mode = True

    def stop_upload(self):
        self._upload_mode = False

    async def close(self):
        if self.transport:
            self.transport.close()

        await self.disconnect_future

    async def wait_connection(self):
        await self.connect_future

    def connection_made(self, transport):
        self.transport = transport
        logger.info("Connected to serial")
        self.connect_future.set_result(True)

    def is_event(self, message):
        return len(message) > 0 and message[0] in EventType.__members__.values()

    def data_received(self, data):
        self.buffer += data

        while True:
            message, eol, leftover = self.buffer.partition(self.EOL)
            if self._upload_mode:
                self.buffer = leftover
                logger.debug("received in upload mode: %s", binascii.hexlify(message))
                self.queue.put_nowait(message)

            if eol == b"":  # EOL not found
                break

            logger.debug("received: %s", binascii.hexlify(message))
            self.buffer = leftover

            if self.is_event(message):
                self.event_message_handler(message)
            else:
                self.queue.put_nowait(message)

    def read_no_wait(self):
        return self.queue.get_nowait()

    async def read(self):
        return await self.queue.get()

    def write(self, data, eol=True):
        if isinstance(data, str):
            data = data.encode()
        self.transport.write(data + self.EOL if eol else b"")
        logger.debug("sent: %s", data)

    def connection_lost(self, exc):
        logger.error("Connection lost")
        if not self.connect_future.done():
            self.connect_future.set_result(False)
        # self.connect_future = asyncio.get_event_loop().create_future()
        if not self.disconnect_future.done():
            self.disconnect_future.set_result(True)
