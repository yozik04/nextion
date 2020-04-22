import asyncio
import binascii
import logging
import struct
import typing
from collections import namedtuple
from pathlib import Path

import serial_asyncio

from .exceptions import CommandFailed, CommandTimeout, ConnectionFailed
from .protocol import EventType, NextionProtocol, ResponseType

IO_TIMEOUT = 0.5  # Background picture change takes 180ms + first variable set after a wakeup takes 240ms + some buffer.
BAUDRATES = [2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400]
ENCODING = 'utf-8'


logger = logging.getLogger("nextion").getChild(__name__)

TouchDataPayload = namedtuple("Touch", "page_id component_id touch_event")
TouchCoordinateDataPayload = namedtuple("TouchCoordinate", "x y touch_event")


class Nextion:
    def __init__(
        self,
        url: str,
        baudrate: int = None,
        event_handler: typing.Callable[[EventType, any], None] = None,
        loop=asyncio.get_event_loop(),
        reconnect_attempts: int = 3,
    ):
        self._loop = loop

        self._url = url
        self._baudrate = baudrate
        self._connection = None
        self._command_lock = asyncio.Lock()
        self.event_handler = event_handler or (
            lambda t, d: logger.info("Event %s data: %s" % (t, str(d)))
        )
        self._reconnect_attempts = reconnect_attempts

        self._sleeping = True
        self.sets_todo = {}

    async def on_startup(self):
        await self.command("bkcmd=3")  # Let's ensure we receive expected responses

    async def on_wakeup(self):
        logger.debug('Updating variables after wakeup: "%s"', str(self.sets_todo))
        for k, v in self.sets_todo.items():
            self._loop.create_task(self.set(k, v))
        self.sets_todo = {}
        self._sleeping = False

    def event_message_handler(self, message):
        logger.debug("Handle event: %s", message)

        typ = message[0]
        if typ == EventType.TOUCH:  # Touch event
            self.event_handler(
                EventType(typ),
                TouchDataPayload._make(struct.unpack("BBB", message[1:])),
            )
        elif typ == EventType.TOUCH_COORDINATE:  # Touch coordinate
            self.event_handler(
                EventType(typ),
                TouchCoordinateDataPayload._make(struct.unpack("HHB", message[1:])),
            )
        elif typ == EventType.TOUCH_IN_SLEEP:  # Touch event in sleep mode
            self.event_handler(
                EventType(typ),
                TouchCoordinateDataPayload._make(struct.unpack("HHB", message[1:])),
            )
        elif typ == EventType.AUTO_SLEEP:  # Device automatically enters into sleep mode
            self._sleeping = True
            self.event_handler(EventType(typ), None)
        elif typ == EventType.AUTO_WAKE:  # Device automatically wake up
            self._loop.create_task(self.on_wakeup())
            self.event_handler(EventType(typ), None)
        elif typ == EventType.STARTUP:  # System successful start up
            self._loop.create_task(self.on_startup())
            self.event_handler(EventType(typ), None)
        elif typ == EventType.SD_CARD_UPGRADE:  # Start SD card upgrade
            self.event_handler(EventType(typ), None)
        else:
            logger.warning("Other event: 0x%02x", typ)

    def _make_protocol(self) -> NextionProtocol:
        return NextionProtocol(event_message_handler=self.event_message_handler)
    
    def set_encoding(self, encoding):
        global ENCODING
        ENCODING = encoding

    def get_encoding(self):
        return ENCODING

    async def _connect_at_baud(self, baud):
        delay_between_connect_attempts = (1000000 / baud + 30) / 1000

        logger.info("Connecting: %s, baud: %s", self._url, baud)
        try:
            _, self._connection = await serial_asyncio.create_serial_connection(
                self._loop, self._make_protocol, url=self._url, baudrate=baud
            )
        except OSError as e:
            if e.errno == 2:
                raise ConnectionFailed(
                    "Failed to open serial connection: %s" % e
                )
            else:
                logger.warning("Baud %s not supported: %s", baud, e)
                return False

        await self._connection.wait_connection()

        self._connection.write("DRAKJHSUYDGBNCJHGJKSHBDN", ENCODING)  # exit active Protocol Reparse and return to passive mode

        await asyncio.sleep(delay_between_connect_attempts)  # (1000000/baud rate)+30ms

        for connect_message in [
            "connect",  # traditional connect instruction
            "\xff\xffconnect"  # connect instruction using the broadcast address of 65535
        ]:
            self._connection.write(connect_message, ENCODING)
            try:
                result = await self._read()
                if result[:6] == b"comok ":
                    return result
                else:
                    logger.warning(
                        "Wrong reply %s to connect attempt", result
                    )
            except asyncio.TimeoutError as e:
                await asyncio.sleep(delay_between_connect_attempts)  # (1000000/baud rate)+30ms

        logger.warning(
            "No valid reply on %d baud. Closing connection", baud
        )
        await self._connection.close()
        return False

    async def connect(self) -> None:
        try:
            baudrates = BAUDRATES.copy()
            if self._baudrate:  # if a baud rate specified put it first in array
                try:
                    baudrates.remove(self._baudrate)
                except ValueError:
                    pass
                baudrates.insert(0, self._baudrate)

            for baud in baudrates:
                result = await self._connect_at_baud(baud)
                if result:
                    self._baudrate = baud
                    break
                else:
                    logger.warning("Baud %d did not work", baud)
            else:
                raise ConnectionFailed("No baud rate suited")

            data = result[7:].decode().split(",")
            logger.info("Address: %s", data[1])
            logger.info("Detected model: %s", data[2])
            logger.info("Firmware version: %s", data[3])
            logger.info("Serial number: %s", data[5])
            logger.debug("Flash size: %s", data[6])

            try:
                await self._command("bkcmd=3", attempts=1)
            except CommandTimeout as e:
                pass  # it is fine
            self._sleeping = await self._command("get sleep")

            logger.info("Successfully connected to the device")
        except ConnectionFailed:
            logger.exception("Connection failed")
            raise
        except:
            logger.exception("Unexpected exception during connect")
            raise

    async def reconnect(self):
        await self._connection.close()
        await self.connect()

    async def _read(self, timeout=IO_TIMEOUT):
        return await asyncio.wait_for(self._connection.read(), timeout=timeout)

    async def get(self, key, timeout=IO_TIMEOUT):
        return await self.command("get %s" % key, timeout=timeout)

    async def set(self, key, value, timeout=IO_TIMEOUT):
        if isinstance(value, str):
            out_value = '"%s"' % value
        elif isinstance(value, float):
            logger.warning("Float is not supported. Converting to string")
            out_value = '"%s"' % str(value)
        elif isinstance(value, int):
            out_value = str(value)
        else:
            raise AssertionError(
                'value type "%s" is not supported for set' % type(value).__name__
            )

        if self._sleeping and key not in ["sleep"]:
            logger.debug(
                'Device sleeps. Scheduling "%s" set for execution after wakeup', key
            )
            self.sets_todo[key] = value
        else:
            return await self.command("%s=%s" % (key, out_value), timeout=timeout)

    async def _command(self, command, timeout=IO_TIMEOUT, attempts=None):
        assert attempts is None or attempts > 0

        attempts_remained = attempts or self._reconnect_attempts
        last_exception = None
        while attempts_remained > 0:
            attempts_remained -= 1
            if isinstance(last_exception, CommandTimeout):
                try:
                    logger.info("Reconnecting")
                    await self.reconnect()
                    last_exception = None
                except ConnectionFailed:
                    logger.error("Reconnect failed")
                    await asyncio.sleep(1)
                    continue

            try:
                while True:
                    logger.debug(
                        "Dropping dangling: %s", self._connection.read_no_wait()
                    )
            except asyncio.QueueEmpty:
                pass

            self._connection.write(command, ENCODING)

            result = None
            data = None
            finished = False

            while not finished:
                try:
                    response = await self._read(timeout=timeout)
                except asyncio.TimeoutError as e:
                    logger.error('Command "%s" timeout.', command)
                    last_exception = CommandTimeout(
                        'Command "%s" response was not received' % command
                    )
                    await asyncio.sleep(IO_TIMEOUT)
                    break

                res_len = len(response)
                if res_len == 0:
                    finished = True
                elif res_len == 1:  # is response code
                    response_code = response[0]
                    if response_code == 0x01:  # success
                        result = True
                        finished = True
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
                        data = struct.unpack("i", raw)[0]
                    else:
                        logger.error(
                            "Unknown data received: %s" % binascii.hexlify(response)
                        )
            else:  # this will run if loop ended successfully
                return data if data is not None else result

        if last_exception is not None:
            raise last_exception

    async def command(self, command, timeout=IO_TIMEOUT, attempts=None):
        async with self._command_lock:
            return await self._command(command, timeout=timeout, attempts=attempts)

    async def sleep(self):
        if self._sleeping:
            return
        await self.set("sleep", 1)
        self._sleeping = True

    async def wakeup(self):
        if not self._sleeping:
            return
        await self.set("sleep", 0)
        await self.on_wakeup()

    async def dim(self, val: int):
        assert 0 <= val <= 100
        await self.set("dim", val)

    async def upload_firmware(self, file):
        p = Path(file)
        if not p.exists():
            raise IOError("File %s does not exist" % file)
        if not p.is_file():
            raise IOError("File %s is not a regular file")
        file_size = p.stat().st_size

        logger.info("About to upload %s(%d bytes)" % (file, file_size))
        await self.set("sleep", 0)
        await asyncio.sleep(0.15)
        await self.set("usup", 1)
        await self.set("ussp", 0)

        self._connection.start_upload()
        try:
            self._connection.write("whmi-wri %d,%d,0" % (file_size, self._baudrate), ENCODING)
            res = await self._read(timeout=1)
            if res != b"\x05":
                raise IOError(
                    "Wrong response to upload command: %s" % binascii.hexlify(res)
                )

            with open(file, "rb") as fh:
                while True:
                    buf = fh.read(4096)
                    if not buf:
                        break
                    self._connection.write(buf, ENCODING, eol=False)

                    timeout = len(buf) * 12 / self._baudrate + 1
                    res = await self._read(timeout=timeout)
                    if res != b"\x05":
                        raise IOError(
                            "Wrong response while uploading chunk: %s"
                            % binascii.hexlify(res)
                        )

        finally:
            self._connection.stop_upload()
