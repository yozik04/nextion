import asyncio
import binascii
import logging
import struct
import typing
from collections import namedtuple
from enum import IntEnum

import serial_asyncio


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


from .exceptions import CommandFailed, CommandTimeout, command_failed_codes

logger = logging.getLogger('nextion').getChild(__name__)


class NextionProtocol(asyncio.Protocol):
    EOL = b'\xff\xff\xff'

    def __init__(self, event_message_handler: typing.Callable):
        self.transport = None
        self.buffer = b''
        self.queue = asyncio.Queue()
        self.connect_future = asyncio.get_event_loop().create_future()
        self.event_message_handler = event_message_handler

    async def wait_connection(self):
        await self.connect_future

    def connection_made(self, transport):
        self.transport = transport
        # self.transport._serial.write_timeout = None
        logger.info("Connected to serial")
        self.connect_future.set_result(True)

    def is_event(self, message):
        return len(message) > 0 and message[0] in EventType.__members__.values()

    def data_received(self, data):
        self.buffer += data
        if self.EOL in self.buffer:
            messages = self.buffer.split(self.EOL)
            for message in messages:
                logger.debug('received: "%s"', binascii.hexlify(message))
                if self.is_event(message):
                    self.event_message_handler(message)
                else:
                    self.queue.put_nowait(message)
            self.buffer = messages[-1]

    def read_no_wait(self):
        return self.queue.get_nowait()

    async def read(self):
        return await self.queue.get()

    def write(self, data):
        if isinstance(data, str):
            data = data.encode()
        self.transport.write(data + self.EOL)
        logger.debug('sent: %s', data)

    def connection_lost(self, exc):
        logger.error('Connection lost')
        self.connect_future = asyncio.get_event_loop().create_future()


TouchDataPayload = namedtuple('Touch', 'page_id component_id touch_event')
TouchCoordinateDataPayload = namedtuple('TouchCoordinate', 'x y touch_event')

class Nextion:
    def __init__(self, url: str, baudrate: int, event_handler: typing.Callable = None):
        self.url = url
        self.baudrate = baudrate
        self.connection = None
        self.command_lock = asyncio.Lock()
        self.event_handler = event_handler or (lambda t, d: logger.info('Event %s data: %s' % t, str(d)))

    def event_message_handler(self, message):
        logger.debug('Handle event: %s', message)

        typ = message[0]
        if typ == EventType.TOUCH:  # Touch event
            self.event_handler(EventType(typ), TouchDataPayload._make(struct.unpack('BBB', message[1:])))
        elif typ == EventType.TOUCH_COORDINATE:  # Touch coordinate
            self.event_handler(EventType(typ), TouchCoordinateDataPayload._make(struct.unpack('HHB', message[1:])))
        elif typ == EventType.TOUCH_IN_SLEEP:  # Touch event in sleep mode
            self.event_handler(EventType(typ), TouchCoordinateDataPayload._make(struct.unpack('HHB', message[1:])))
        elif typ == EventType.AUTO_SLEEP:  # Device automatically enters into sleep mode
            self.event_handler(EventType(typ), None)
        elif typ == EventType.AUTO_SLEEP:  # Device automatically wake up
            self.event_handler(EventType(typ), None)
        elif typ == EventType.STARTUP:  # System successful start up
            self.event_handler(EventType(typ), None)
        elif typ == EventType.SD_CARD_UPGRADE:  # Start SD card upgrade
            self.event_handler(EventType(typ), None)
        else:
            logger.warn('Other event: 0x%02x', typ)

    def _make_protocol(self) -> NextionProtocol:
        return NextionProtocol(event_message_handler=self.event_message_handler)

    async def connect(self):
        loop = asyncio.get_event_loop()
        _, self.connection = await serial_asyncio.create_serial_connection(loop, self._make_protocol, url=self.url,
                                                                           baudrate=self.baudrate)
        await self.connection.wait_connection()

        self.connection.write('')

        async with self.command_lock:
            self.connection.write('connect')
            result = await self._read()

        assert result[:6] == b'comok '

        data = result[7:].decode().split(",")
        logger.info('Detected model: %s', data[2])
        logger.info('Firmware version: %s', data[3])
        logger.info('Serial number: %s', data[5])
        logger.debug('Flash size: %s', data[6])

        await self.command('bkcmd=3')

        logger.info("Successfully connected to the device")

    async def _read(self, timeout=0.1):
        try:
            return await asyncio.wait_for(self.connection.read(), timeout=timeout)
        except asyncio.TimeoutError as e:
            raise CommandTimeout("Command response was not received") from e

    async def get(self, key):
        return await self.command('get %s' % key)

    async def set(self, key, value):
        if isinstance(value, str):
            value = '"%s"' % value
        elif isinstance(value, float):
            logger.warn('Float is not supported. Converting to string')
            value = '"%s"' % str(value)
        elif isinstance(value, int):
            value = str(value)
        else:
            raise AssertionError('value type "%s" is not supported for set' % type(value).__name__)
        return await self.command('%s=%s' % (key, value))

    async def command(self, command, timeout=0.1):
        async with self.command_lock:
            try:
                while True:
                    logger.debug("Dropping dangling: %s", self.connection.read_no_wait())
            except asyncio.QueueEmpty:
                pass

            self.connection.write(command)

            result = None
            data = None
            finished = False
            try:
                while not finished:
                    response = await self._read(timeout=timeout)

                    res_len = len(response)
                    if res_len == 0:
                        finished = True
                    elif res_len == 1:  # is response code
                        response_code = response[0]
                        if response_code == 0x01:  # success
                            result = True
                        else:
                            error = command_failed_codes.get(response_code)
                            if error:
                                raise CommandFailed('"%s" command failed: %s' % (command, error))
                            else:
                                logger.error("Unknown response code: %s" % binascii.hexlify(response_code))
                                result = False
                    else:
                        typ = response[0]
                        raw = response[1:]
                        if typ == ResponseType.PAGE:  # Page ID
                            data = raw[1]
                        elif typ == ResponseType.STRING:  # string
                            data = raw.decode()
                        elif typ == ResponseType.NUMBER:  # number
                            data = struct.unpack('i', raw)[0]
                        else:
                            logger.error("Unknown data received: %s" % binascii.hexlify(response))

            except CommandTimeout as e:
                logger.error('Timeout to receive response code for command %s', command)

            return data or result

    async def sleep(self, on: bool):
        await self.set('sleep', 1 if on else 0)
        await asyncio.sleep(0.15)

    async def dim(self, val: int):
        assert 0 <= val <= 100

        await self.set('dim', val)
