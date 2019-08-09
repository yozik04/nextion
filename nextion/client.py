import asyncio
import binascii
import logging
import struct
import typing

import serial_asyncio

from .exceptions import CommandFailed, CommandTimeout, command_failed_codes

logger = logging.getLogger('nextion').getChild(__name__)


class NextionProtocol(asyncio.Protocol):
    EOL = b'\xff\xff\xff'

    def __init__(self, event_handler: typing.Callable):
        self.transport = None
        self.buffer = b''
        self.queue = asyncio.Queue()
        self.connect_future = asyncio.get_event_loop().create_future()
        self.event_handler = event_handler

    def connection_made(self, transport):
        self.transport = transport
        # self.transport._serial.write_timeout = None
        logger.info("Connected to serial")
        self.connect_future.set_result(True)

    def is_event(self, message):
        return len(message) > 0 and message[0] in [0x65, 0x67, 0x68, 0x86, 0x87, 0x88, 0x89]

    def data_received(self, data):
        self.buffer += data
        if self.EOL in self.buffer:
            messages = self.buffer.split(self.EOL)
            for message in messages:
                logger.debug('received: "%s"', binascii.hexlify(message))
                if self.is_event(message):
                    self.event_handler(message)
                else:
                    self.queue.put_nowait(message)
            self.buffer = messages[-1]

    def write(self, data):
        if isinstance(data, str):
            data = data.encode()
        self.transport.write(data + self.EOL)
        logger.debug('sent: %s', data)

    def connection_lost(self, exc):
        logger.error('Connection lost')
        self.connect_future = asyncio.get_event_loop().create_future()


class Nextion:
    connection: NextionProtocol

    def __init__(self, url, baudrate):
        self.url = url
        self.baudrate = baudrate
        self.connection = None
        self.command_lock = asyncio.Lock()

    def event_handler(self, message):
        logger.debug('Handle event: %s', message)

    def make_protocol(self) -> NextionProtocol:
        return NextionProtocol(event_handler=self.event_handler)

    async def connect(self):
        loop = asyncio.get_event_loop()
        _, self.connection = await serial_asyncio.create_serial_connection(loop, self.make_protocol, url=self.url,
                                                                           baudrate=self.baudrate)
        await self.connection.connect_future

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
            return await asyncio.wait_for(self.connection.queue.get(), timeout=timeout)
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
                    logger.debug("Dropping dangling: %s", self.connection.queue.get_nowait())
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
                        if typ == 0x66:  # Page ID
                            data = raw[1]
                        elif typ == 0x70:  # string
                            data = raw.decode()
                        elif typ == 0x71:  # number
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
