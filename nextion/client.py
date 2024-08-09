import asyncio
import binascii
from collections import namedtuple
from dataclasses import dataclass
from io import BufferedReader
import logging
import os
import struct
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union
import warnings

import serial_asyncio_fast as serial_asyncio

from nextion.constants import BAUD_RATES, IO_TIMEOUT
from nextion.exceptions import (
    CommandFailed,
    CommandTimeout,
    ConnectionFailed,
    InvalidReply,
    NoValidReply,
    UnsupportedBaudRate,
)
from nextion.protocol import BasicProtocol, EventType, NextionProtocol, ResponseType

logger = logging.getLogger("nextion").getChild(__name__)

TouchDataPayload = namedtuple("TouchDataPayload", "page_id component_id touch_event")
TouchCoordinateDataPayload = namedtuple("TouchCoordinateDataPayload", "x y touch_event")

ValueType = Union[str, float, int]


async def _default_event_handler(type_, data):
    logger.info(f"Event {type_} data: {str(data)}")


@dataclass
class DeviceInfo:
    address: str
    model: str
    firmware_version: str
    serial_number: str
    flash_size: str


class Nextion:
    """A class for interacting with a Nextion device"""

    device_info: Optional[DeviceInfo]
    _pending_sets: Dict[str, ValueType]

    def __init__(
        self,
        url: str,
        baud_rate: Optional[int] = None,
        event_handler: Callable[
            [EventType, Any], Union[Awaitable[None], None]
        ] = _default_event_handler,
        reconnect_attempts: int = 3,
        encoding: str = "ascii",
    ):
        self._url = url
        self._baud_rate = baud_rate
        self._connection: Optional[NextionProtocol] = None
        self._command_lock = asyncio.Lock()
        self._reconnect_attempts = reconnect_attempts
        self._encoding = encoding

        self.event_handler = event_handler
        self.device_info = None

        self._sleeping = True
        self._pending_sets = {}

    async def _on_startup(self) -> None:
        await self.command("bkcmd=3")  # Let's ensure we receive expected responses

    async def _on_wakeup(self) -> None:
        logger.debug('Updating variables after wakeup: "%s"', str(self._pending_sets))
        for k, v in self._pending_sets.items():
            asyncio.create_task(self.set(k, v))
        self._pending_sets = {}
        self._sleeping = False

    def _handle_event(self, message) -> None:
        logger.debug("Handle event: %s", message)

        typ = message[0]
        if typ == EventType.TOUCH:  # Touch event
            self._schedule_event_message_handler(
                EventType(typ),
                TouchDataPayload._make(struct.unpack("BBB", message[1:])),
            )
        elif typ == EventType.TOUCH_COORDINATE:  # Touch coordinate
            self._schedule_event_message_handler(
                EventType(typ),
                TouchCoordinateDataPayload._make(struct.unpack("HHB", message[1:])),
            )
        elif typ == EventType.TOUCH_IN_SLEEP:  # Touch event in sleep mode
            self._schedule_event_message_handler(
                EventType(typ),
                TouchCoordinateDataPayload._make(struct.unpack("HHB", message[1:])),
            )
        elif typ == EventType.AUTO_SLEEP:  # Device automatically enters into sleep mode
            self._sleeping = True
            self._schedule_event_message_handler(EventType(typ), None)
        elif typ == EventType.AUTO_WAKE:  # Device automatically wake up
            asyncio.create_task(self._on_wakeup())
            self._schedule_event_message_handler(EventType(typ), None)
        elif typ == EventType.STARTUP:  # System successful start up
            asyncio.create_task(self._on_startup())
            self._schedule_event_message_handler(EventType(typ), None)
        elif typ == EventType.SD_CARD_UPGRADE:  # Start SD card upgrade
            self._schedule_event_message_handler(EventType(typ), None)
        else:
            logger.warning("Other event: 0x%02x", typ)

    def _schedule_event_message_handler(self, type_, data) -> None:
        asyncio.create_task(self._call_event_handler(type_, data))

    async def _call_event_handler(self, type_, data) -> None:
        result = self.event_handler(type_, data)
        if asyncio.iscoroutine(result):
            await result

    async def connect(self) -> None:
        """Connect to the device"""
        try:
            await self._try_connect_on_different_baudrates()

            assert self.device_info
            logger.info(
                "Address: %s", self.device_info.address
            )  # <unknown>-<address>, if address then all commands need to be
            # prepended with address. See https://nextion.tech/2017/12/08/nextion-hmi-upload-protocol-v1-1/
            logger.info("Detected model: %s", self.device_info.model)
            logger.info("Firmware version: %s", self.device_info.firmware_version)
            logger.info("Serial number: %s", self.device_info.serial_number)
            logger.info("Flash size: %s", self.device_info.flash_size)

            try:
                await self._command("bkcmd=3", attempts=1)
            except CommandTimeout:
                pass  # it is fine

            await self._update_sleep_status()

            logger.info("Successfully connected to the device")
        except ConnectionFailed:
            logger.exception("Connection failed")
            raise
        except Exception:
            logger.exception("Unexpected exception during connect")
            raise

    async def _try_connect_on_different_baudrates(self) -> None:
        baud_rates = self._get_priority_ordered_baud_rates()

        for baud in baud_rates:
            try:
                await self._connect_at_baud(baud)
                self._baud_rate = baud
                break
            except ConnectionFailed:
                logger.warning("Baud %d did not work", baud)
        else:
            raise ConnectionFailed("No baud rate suited")

    async def _connect_at_baud(self, baud: int) -> None:
        delay_between_connect_attempts = (1000000 / baud + 30) / 1000

        logger.info("Connecting: %s, baud: %s", self._url, baud)
        try:
            self._connection = await self._create_serial_connection(baud)
        except OSError as e:
            if e.errno == 2:
                raise ConnectionFailed("Failed to open serial connection") from e
            else:
                logger.warning("Baud %s not supported: %s", baud, e)
                raise UnsupportedBaudRate(f"Baud {baud} not supported") from e

        await self._connection.wait_connection()

        self._write_command_raw(
            b"DRAKJHSUYDGBNCJHGJKSHBDN"
        )  # exit active Protocol Reparse and return to passive mode
        try:
            await self._read_packet(
                timeout=delay_between_connect_attempts
            )  # We do not care what response will be here
        except asyncio.TimeoutError:
            pass

        await asyncio.sleep(delay_between_connect_attempts)  # (1000000/baud rate)+30ms

        await self._attempt_connect_messages(delay_between_connect_attempts)

    async def _create_serial_connection(self, baud: int):
        _, connection = await serial_asyncio.create_serial_connection(
            asyncio.get_event_loop(), self._make_protocol, url=self._url, baudrate=baud
        )

        return connection

    def _make_protocol(self) -> NextionProtocol:
        return NextionProtocol(event_message_handler=self._handle_event)

    async def _attempt_connect_messages(
        self, delay_between_connect_attempts: float
    ) -> None:
        for connect_message in [
            b"connect",  # traditional connect instruction
            b"\xff\xffconnect",  # connect instruction using the broadcast address of 65535
        ]:
            self._write_command_raw(connect_message)
            try:
                result = await self._read_packet(timeout=delay_between_connect_attempts)
                if result[:6] == b"comok ":
                    data = result[7:].decode().split(",")
                    self.device_info = DeviceInfo(
                        address=data[1],
                        model=data[2],
                        firmware_version=data[3],
                        serial_number=data[5],
                        flash_size=data[6],
                    )
                    return
                else:
                    raise InvalidReply(f"Wrong reply {result!r} to connect attempt")
            except (asyncio.TimeoutError, InvalidReply) as e:
                logger.warning(e)
        raise NoValidReply("No valid reply received during connection attempts")

    async def _update_sleep_status(self) -> None:
        self._sleeping = bool(await self._command("get sleep"))

    def _get_priority_ordered_baud_rates(self) -> List[int]:
        baud_rates = BAUD_RATES.copy()
        if self._baud_rate:  # if a baud rate specified put it first in array
            try:
                baud_rates.remove(self._baud_rate)
            except ValueError:
                pass
            baud_rates.insert(0, self._baud_rate)
        return baud_rates

    async def reconnect(self) -> None:
        """Reconnect to the device"""
        await self._connection.close()
        await self.connect()

    async def disconnect(self) -> None:
        """Disconnect from the device"""
        if self._connection:
            await self._connection.close()

    async def _read_packet(self, timeout=IO_TIMEOUT) -> bytes:
        """Read a packet from the device"""
        if not self._connection:
            raise ConnectionFailed("Connection is not established")

        return await asyncio.wait_for(self._connection.read(), timeout=timeout)

    async def get(self, key: str, timeout=IO_TIMEOUT):
        """Get a value from the device"""
        return await self.command(f"get {key}", timeout=timeout)

    async def set(
        self, key: str, value: ValueType, timeout=IO_TIMEOUT
    ) -> Union[ValueType, None]:
        """Set a value on the device

        Returns None is device is sleeping and set is scheduled for execution after wakeup
        """
        if isinstance(value, str):
            out_value = f'"{value}"'
        elif isinstance(value, float):
            logger.warning("Float is not supported. Converting to string")
            out_value = f'"{value}"'
        elif isinstance(value, int):
            out_value = str(value)
        else:
            raise TypeError(
                f'value type "{type(value).__name__}" is not supported for set'
            )

        if self._sleeping and key not in ["sleep"]:
            logger.debug(
                f'Device sleeps. Scheduling "{key}" set for execution after wakeup'
            )
            self._pending_sets[key] = value
            return None
        else:
            return await self.command(f"{key}={out_value}", timeout=timeout)

    async def _command(
        self, command: str, timeout=IO_TIMEOUT, attempts: Union[int, None] = None
    ) -> Union[ValueType, None]:
        attempts_remained = (
            attempts if attempts is not None else self._reconnect_attempts
        )
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

            self._flush_read_buffer()

            self._write_command_raw(command.encode(self._encoding))

            result = None
            data: Union[ValueType, None] = None
            finished = False

            while not finished:
                try:
                    response = await self._read_packet(timeout=timeout)
                except asyncio.TimeoutError:
                    logger.error('Command "%s" timeout.', command)
                    last_exception = CommandTimeout(
                        f'Command "{command}" response was not received'
                    )
                    await asyncio.sleep(IO_TIMEOUT)
                    break

                res_len = len(response)
                if res_len == 0:
                    finished = True
                    if result is None:
                        result = True
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
                        data = int(raw[0])
                    elif type_ == ResponseType.STRING:  # string
                        data = raw.decode(self._encoding)
                    elif type_ == ResponseType.NUMBER:  # number
                        data = struct.unpack("i", raw)[0]
                    else:
                        logger.error(
                            "Unknown data received: %s"
                            % binascii.hexlify(response).decode("utf-8")
                        )
                    if command.partition(" ")[0] in ["get", "sendme"]:
                        finished = True
            else:  # this will run if while loop ended successfully
                return data if data is not None else result

        if last_exception is not None:
            raise last_exception

        return None

    def _write_command_raw(self, command: bytes) -> None:
        """Write a raw command to the device"""
        assert self._connection

        self._connection.write(command)

    def _flush_read_buffer(self) -> None:
        """Flush the read buffer"""
        try:
            while True:
                logger.debug("Flushing message: %s", self._connection.read_no_wait())
        except asyncio.QueueEmpty:
            pass

    async def command(self, command: str, timeout=IO_TIMEOUT, attempts=None):
        """Send a command to the device"""
        async with self._command_lock:
            return await self._command(command, timeout=timeout, attempts=attempts)

    @property
    def sleeping(self) -> bool:
        """Check if the device is sleeping"""
        return self._sleeping

    def is_sleeping(self) -> bool:
        """Check if the device is sleeping"""
        warnings.warn(
            "The 'is_sleeping' method is deprecated and will be removed in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._sleeping

    async def sleep(self) -> None:
        """Put the device to sleep"""
        if self._sleeping:
            return
        await self.set("sleep", 1)
        self._sleeping = True

    async def wakeup(self) -> None:
        """Wake the device up"""
        if not self._sleeping:
            return
        await self.set("sleep", 0)
        await self._on_wakeup()

    async def dim(self, val: int) -> None:
        """Set the device brightness"""
        assert 0 <= val <= 100
        await self.set("dim", val)

    def _make_upload_protocol(self) -> BasicProtocol:
        return BasicProtocol()

    async def upload_firmware(self, file: BufferedReader, upload_baud=None):
        """Upload firmware to the device"""
        upload_baud = upload_baud or self._baud_rate
        assert upload_baud in BAUD_RATES

        file_size = os.fstat(file.fileno()).st_size

        logger.info(f"About to upload {file_size} bytes")
        await self.set("sleep", 0)
        await asyncio.sleep(0.15)
        try:
            await self.set("usup", 1)
            await self.set("ussp", 0)
        except CommandFailed as e:
            logger.warning(f"Additional sleep configuration failed: {e}")

        self._write_command_raw(b"whmi-wri %d,%d,0" % (file_size, upload_baud))
        logger.info(f"Reconnecting at new baud rate: {upload_baud}" % (upload_baud))
        assert self._connection
        await self._connection.close()
        _, self._connection = await serial_asyncio.create_serial_connection(
            asyncio.get_event_loop(),
            self._make_upload_protocol,
            url=self._url,
            baudrate=upload_baud,
        )
        assert self._connection

        res = await self._read_packet(timeout=1)
        if res != b"\x05":
            raise OSError(
                "Wrong response to upload command: %s"
                % binascii.hexlify(res).decode("utf-8")
            )

        logger.info("Device is ready to accept upload")

        uploaded_bytes = 0
        chunk_size = 4096
        try:
            while True:
                buf = file.read(chunk_size)
                if not buf:
                    break
                self._connection.write(buf, eol=False)

                timeout = len(buf) * 12 / upload_baud + 1
                res = await self._read_packet(timeout=timeout)
                if res != b"\x05":
                    raise OSError(
                        "Wrong response while uploading chunk: %s"
                        % binascii.hexlify(res).decode("utf-8")
                    )

                uploaded_bytes += len(buf)
                logger.info("Uploaded: %.1f%%", uploaded_bytes / file_size * 100)
        finally:
            file.close()

        logger.info("Successfully uploaded %d bytes" % uploaded_bytes)
