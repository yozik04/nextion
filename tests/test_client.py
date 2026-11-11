import asyncio
from unittest.mock import AsyncMock, Mock, call

import pytest

from nextion import Nextion
from nextion.client import TouchDataPayload
from nextion.exceptions import CommandFailed, ConnectionFailed
from nextion.protocol.nextion import EventType, NextionProtocol


@pytest.fixture
async def transport() -> Mock:
    return Mock()


@pytest.fixture
def event_handler():
    return Mock()


@pytest.fixture
async def protocol(transport) -> NextionProtocol:
    protocol = NextionProtocol(
        lambda x: None
    )  # Assuming a lambda for the event_message_handler
    protocol.connection_made(transport)
    protocol.write = Mock()

    return protocol


@pytest.fixture
async def client(protocol: NextionProtocol, event_handler) -> Nextion:
    client = Nextion("/dev/ttyS1", 9600, event_handler)
    client._connection = protocol
    protocol.event_message_handler = client._handle_event
    assert client.sleeping
    return client


@pytest.mark.parametrize(
    "response_data, expected_result, variable",
    [
        (b"\x71\x01\x00\x00\x00\xff\xff\xff", 1, "sleep"),
        (b"\x71\x01\x00\x00\x00\xff\xff\xff\01\xff\xff\xff\xff\xff\xff", 1, "sleep"),
        (b"\x71\xa5\xff\xff\xff\xff\xff\xff", -91, "var1"),
        (b"\x71\xa5\xff\xff\xff\xff\xff\xff\01\xff\xff\xff\xff\xff\xff", -91, "var1"),
        (b"\x70\x34\x30\xff\xff\xff", "40", "t16.txt"),
        (b"\x70\x34\x30\xff\xff\xff\01\xff\xff\xff\xff\xff\xff", "40", "t16.txt"),
    ],
)
async def test_get(client, protocol, response_data, expected_result, variable):
    protocol.write.side_effect = lambda _: protocol.data_received(response_data)
    result = await client.get(variable)
    protocol.write.assert_called_once_with(f"get {variable}".encode())
    assert result == expected_result


@pytest.mark.parametrize(
    "response_data, expected_result, command",
    [
        (b"\xff\xff\xff", True, "lowpower=0"),
        (b"\x66\x05\xff\xff\xff", 5, "sendme"),
        (b"\x66\x05\xff\xff\xff\01\xff\xff\xff\xff\xff\xff", 5, "sendme"),
    ],
)
async def test_command(client, protocol, response_data, expected_result, command):
    protocol.write.side_effect = lambda _: protocol.data_received(response_data)
    assert await client.command(command) == expected_result
    protocol.write.assert_called_once_with(command.encode())


async def test_command_failed(client, protocol):
    protocol.write.side_effect = lambda _: protocol.data_received(b"\x03\xff\xff\xff")
    with pytest.raises(CommandFailed):
        await client.command("page 2")


@pytest.mark.parametrize(
    "response_data",
    [
        (b"\x01\xff\xff\xff"),
        (b"\x01\xff\xff\xff\01\xff\xff\xff\xff\xff\xff"),
    ],
)
async def test_wakeup(client, protocol, response_data):
    protocol.write.side_effect = lambda _: protocol.data_received(response_data)
    await client.wakeup()
    protocol.write.assert_called_once_with(b"sleep=0")


async def test_sleep(client, protocol):
    protocol.write.side_effect = lambda _: protocol.data_received(b"\x01\xff\xff\xff")
    await client.wakeup()
    assert not client.sleeping
    await client.sleep()
    protocol.write.assert_has_calls([call(b"sleep=0"), call(b"sleep=1")])


async def test_dim(client, protocol):
    protocol.write.side_effect = lambda _: protocol.data_received(b"\x01\xff\xff\xff")
    await client.wakeup()
    await client.dim(50)
    protocol.write.assert_has_calls([call(b"sleep=0"), call(b"dim=50")])


@pytest.mark.parametrize(
    "response_data, variable, value",
    [
        (b"\x01\xff\xff\xff", "var.txt", "Hello"),
        (b"\x01\xff\xff\xff", "num.txt", -91),
        (b"\x01\xff\xff\xff", "num.txt", 5.123),
    ],
)
async def test_set_during_sleep(client, protocol, response_data, variable, value):
    protocol.write.side_effect = lambda _: protocol.data_received(response_data)
    await client.set(variable, value)
    protocol.write.assert_not_called()
    await client.wakeup()
    await asyncio.sleep(0)  # Allow background tasks to complete

    expected_value = value
    if isinstance(expected_value, (str, float)):
        expected_value = f'"{expected_value}"'

    protocol.write.assert_has_calls(
        [call(b"sleep=0"), call(f"{variable}={expected_value}".encode())]
    )


async def test_auto_wake_event(client, protocol):
    protocol.write.side_effect = lambda _: protocol.data_received(b"\x01\xff\xff\xff")
    await client.set("var.txt", 30)
    protocol.write.assert_not_called()

    # Simulate wake event received
    protocol.data_received(b"\x87\xff\xff\xff")
    await asyncio.sleep(0)  # Allow background tasks to complete
    assert not client.sleeping

    protocol.write.assert_called_once_with(b"var.txt=30")


async def test_event_handler(client, protocol, event_handler):
    event_handler_called = asyncio.Future()

    def event_handler_called_set_result(*args):
        event_handler_called.set_result(args)

    event_handler.side_effect = event_handler_called_set_result

    protocol.data_received(b"\x65\x01\x03\x01\xff\xff\xff")
    await asyncio.wait_for(event_handler_called, timeout=0.1)
    assert event_handler_called.result() == (
        EventType.TOUCH,
        TouchDataPayload(page_id=1, component_id=3, touch_event=1),
    )


async def test_async_event_handler(client, protocol, event_handler):
    event_handler_called = asyncio.Future()

    async def event_handler_called_set_result(*args):
        event_handler_called.set_result(args)

    event_handler.side_effect = event_handler_called_set_result

    protocol.data_received(b"\x65\x01\x03\x01\xff\xff\xff")
    await asyncio.wait_for(event_handler_called, timeout=0.1)
    assert event_handler_called.result() == (
        EventType.TOUCH,
        TouchDataPayload(page_id=1, component_id=3, touch_event=1),
    )


async def test_event_handler_awaits_future(client, event_handler):
    future = asyncio.Future()
    event_handler.return_value = future
    task = asyncio.create_task(client._call_event_handler(EventType.AUTO_WAKE, None))
    await asyncio.sleep(0)
    assert not task.done()
    future.set_result(None)
    await task


async def test_command_after_disconnect_raises_connection_failed(client, protocol):
    protocol.close = AsyncMock()
    await client.disconnect()
    with pytest.raises(ConnectionFailed, match="Connection is not established"):
        await client.command("get sleep")
    protocol.write.assert_not_called()


class FakeUploadTransport:
    """Serial transport that replies like a Nextion device during an upload."""

    def __init__(self, protocol):
        self.protocol = protocol
        self.serial = Mock(baudrate=9600)
        self.serial.flush.side_effect = self._on_flush
        self.written = []
        self.flushed_before_baud_change = False

    def _on_flush(self):
        self.flushed_before_baud_change = self.serial.baudrate == 9600

    def set_protocol(self, protocol):
        self.protocol = protocol

    def get_write_buffer_size(self):
        return 0

    def write(self, data):
        self.written.append(data)
        if data.startswith(b"whmi-wri"):
            # The ready byte arrives at the upload baud straight after the switch.
            asyncio.get_running_loop().call_soon(self._reply_ready)
        elif self.serial.baudrate == 115200:
            self.protocol.data_received(b"\x05")
        else:
            self.protocol.data_received(b"\x01\xff\xff\xff")

    def _reply_ready(self):
        assert self.serial.baudrate == 115200
        self.protocol.data_received(b"\x05")


async def test_upload_firmware_switches_baud_in_place(tmp_path):
    firmware = tmp_path / "fw.tft"
    firmware.write_bytes(b"a" * 4096 + b"b" * 10)

    client = Nextion("/dev/ttyS1", 9600)
    client._sleeping = False
    protocol = NextionProtocol(client._handle_event)
    transport = FakeUploadTransport(protocol)
    protocol.connection_made(transport)
    client._connection = protocol

    with firmware.open("rb") as file:
        await client.upload_firmware(file, 115200)

    assert transport.flushed_before_baud_change
    assert transport.serial.baudrate == 115200
    assert b"whmi-wri 4106,115200,0\xff\xff\xff" in transport.written
    assert transport.written[-2:] == [b"a" * 4096, b"b" * 10]
    assert client._connection is transport.protocol


async def test_upload_firmware_rejects_empty_file(tmp_path):
    firmware = tmp_path / "empty.tft"
    firmware.touch()
    client = Nextion("/dev/ttyS1", 9600)
    client._sleeping = False
    protocol = NextionProtocol(client._handle_event)
    transport = FakeUploadTransport(protocol)
    protocol.connection_made(transport)
    client._connection = protocol

    with firmware.open("rb") as file:
        with pytest.raises(ValueError, match="Firmware file is empty"):
            await client.upload_firmware(file, 115200)

    assert transport.written == []


async def test_encoding_setter_is_used_for_commands(client, protocol):
    protocol.write.side_effect = lambda data: protocol.data_received(
        b"\x70\x32\x31\xb0C\xff\xff\xff"
        if data.startswith(b"get")
        else b"\x01\xff\xff\xff"
    )
    client._sleeping = False
    assert client.encoding == "ascii"

    client.encoding = "latin-1"

    assert await client.get("t0.txt") == "21°C"
    await client.set("t0.txt", "21°C")
    protocol.write.assert_called_with(b't0.txt="21\xb0C"')
