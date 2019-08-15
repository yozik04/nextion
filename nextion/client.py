import asyncio
import binascii
import logging
import struct
import typing
from collections import namedtuple

import serial_asyncio

TIME_TO_RECOVER_FROM_SLEEP = 0.15

from .exceptions import CommandFailed, CommandTimeout
from .protocol import NextionProtocol, EventType, ResponseType

logger = logging.getLogger('nextion').getChild(__name__)

TouchDataPayload = namedtuple('Touch', 'page_id component_id touch_event')
TouchCoordinateDataPayload = namedtuple('TouchCoordinate', 'x y touch_event')


class Nextion:
    def __init__(self, url: str, baudrate: int, event_handler: typing.Callable = None, loop=asyncio.get_event_loop()):
        self._loop = loop

        self._url = url
        self._baudrate = baudrate
        self._connection = None
        self._command_lock = asyncio.Lock()
        self.event_handler = event_handler or (lambda t, d: logger.info('Event %s data: %s' % (t, str(d))))

        self._sleeping = True
        self.sets_todo = {}

    async def on_wakeup(self):
        await asyncio.sleep(TIME_TO_RECOVER_FROM_SLEEP)  # do not execute next messages until full wakeup
        for k, v in self.sets_todo.items():
            self._loop.create_task(self.set(k, v))
        self.sets_todo = {}
        self._sleeping = False

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
            self._sleeping = True
            self.event_handler(EventType(typ), None)
        elif typ == EventType.AUTO_WAKE:  # Device automatically wake up
            self._loop.create_task(self.on_wakeup())
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
        _, self._connection = await serial_asyncio.create_serial_connection(self._loop, self._make_protocol,
                                                                            url=self._url,
                                                                            baudrate=self._baudrate)
        await self._connection.wait_connection()

        self._connection.write('')

        async with self._command_lock:
            self._connection.write('connect')
            try:
                result = await self._read()
            except asyncio.TimeoutError as e:
                raise CommandTimeout('Connect timeout') from e

        assert result[:6] == b'comok '

        data = result[7:].decode().split(",")
        logger.info('Detected model: %s', data[2])
        logger.info('Firmware version: %s', data[3])
        logger.info('Serial number: %s', data[5])
        logger.debug('Flash size: %s', data[6])

        try:
            await self.command('bkcmd=3')
        except CommandTimeout as e:
            logging.debug('Command "bkcmd=3" timeout')
        self._sleeping = await self.get('sleep')

        logger.info("Successfully connected to the device")

    async def _read(self, timeout=0.1):
        return await asyncio.wait_for(self._connection.read(), timeout=timeout)

    async def get(self, key):
        return await self.command('get %s' % key)

    async def set(self, key, value):
        if isinstance(value, str):
            out_value = '"%s"' % value
        elif isinstance(value, float):
            logger.warn('Float is not supported. Converting to string')
            out_value = '"%s"' % str(value)
        elif isinstance(value, int):
            out_value = str(value)
        else:
            raise AssertionError('value type "%s" is not supported for set' % type(value).__name__)

        if self._sleeping and key not in ['sleep']:
            logging.debug('Device sleeps. Scheduling "%s" set for execution after wakeup', key)
            self.sets_todo[key] = value
        else:
            return await self.command('%s=%s' % (key, out_value))

    async def command(self, command, timeout=0.1):
        async with self._command_lock:
            try:
                while True:
                    logger.debug("Dropping dangling: %s", self._connection.read_no_wait())
            except asyncio.QueueEmpty:
                pass

            self._connection.write(command)

            result = None
            data = None
            finished = False

            while not finished:
                try:
                    response = await self._read(timeout=timeout)
                except asyncio.TimeoutError as e:
                    raise CommandTimeout('Command "%s" response was not received' % command) from e

                res_len = len(response)
                if res_len == 0:
                    finished = True
                elif res_len == 1:  # is response code
                    response_code = response[0]
                    if response_code == 0x01:  # success
                        result = True
                    else:
                        raise CommandFailed(command, response_code)
                else:
                    type_ = response[0]
                    raw = response[1:]
                    if type_ == ResponseType.PAGE:  # Page ID
                        data = raw[1]
                    elif type_ == ResponseType.STRING:  # string
                        data = raw.decode()
                    elif type_ == ResponseType.NUMBER:  # number
                        data = struct.unpack('i', raw)[0]
                    else:
                        logger.error("Unknown data received: %s" % binascii.hexlify(response))

            return data or result

    async def sleep(self):
        if self._sleeping:
            return
        await self.set('sleep', 1)
        self._sleeping = True

    async def wakeup(self):
        if not self._sleeping:
            return
        await self.set('sleep', 0)
        await self.on_wakeup()

    async def dim(self, val: int):
        assert 0 <= val <= 100
        await self.set('dim', val)
