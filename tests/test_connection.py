import asyncio
import binascii
import logging
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from nextion import Nextion
from nextion.client import DeviceInfo
from nextion.exceptions import CommandTimeout, NoValidReply
from nextion.protocol import BasicProtocol

logger = logging.getLogger("nextion").getChild(__name__)


class BaseDummyNextionProtocol(BasicProtocol):
    def __init__(self, responses, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.responses = responses

    def write(self, data: bytes, eol=True):
        logger.debug("sent: %s" % (data))
        response = self.responses.get(data)
        if response:
            if isinstance(response, list):
                for r in response:
                    self.data_received(r)
            else:
                self.data_received(response)
        else:
            logger.error(f"write with no response(eol={eol}): {data!r}")


class DummyNextionProtocol_1_61_1(BaseDummyNextionProtocol):
    def __init__(self, *args, **kwargs):
        responses = {
            b"DRAKJHSUYDGBNCJHGJKSHBDN": b"\x1a",
            b"connect": binascii.unhexlify(
                "636f6d6f6b20312c343131332d302c4e5831303630503130315f303131522c3133322c31303530312c353531363334303142333939453535432c3133313037323030302d30"
            ),
            b"bkcmd=3": b"\x01",
            b"get sleep": b"\x71\x00\x00\x00\x00",
        }
        self.expected_device_info = DeviceInfo(
            address="4113-0",
            model="NX1060P101_011R",
            firmware_version="132",
            serial_number="55163401B399E55C",
            flash_size="131072000-0",
        )
        super().__init__(responses, *args, **kwargs)


class DummyOldNextionProtocol(BaseDummyNextionProtocol):
    def __init__(self, *args, **kwargs):
        responses = {
            b"DRAKJHSUYDGBNCJHGJKSHBDN": b"\x1a",
            b"connect": binascii.unhexlify(
                "636f6d6f6b20312c36372d302c4e5834383237543034335f303131522c3133302c36313438382c453436383543423335423631333633362c3136373737323136"
            ),
            b"bkcmd=3": b"\x01",
            b"thup=1": b"\x01",
            b"get sleep": [b"\x71\x00\x00\x00\x00", b"\x01"],
        }
        self.expected_device_info = DeviceInfo(
            address="67-0",
            model="NX4827T043_011R",
            firmware_version="130",
            serial_number="E4685CB35B613636",
            flash_size="16777216",
        )
        super().__init__(responses, *args, **kwargs)


@pytest.fixture
def create_serial_connection():
    with patch(
        "serial_asyncio_fast.create_serial_connection"
    ) as create_serial_connection:
        yield create_serial_connection


@pytest.fixture
def protocol_1_61_1():
    with patch(
        "nextion.client.NextionProtocol", DummyNextionProtocol_1_61_1()
    ) as protocol:
        yield protocol


@pytest.fixture
def protocol_older():
    with patch("nextion.client.NextionProtocol", DummyOldNextionProtocol()) as protocol:
        yield protocol


async def connect_and_test(client: Nextion, protocol, create_serial_connection):
    async def on_connection_made(*args, **kwargs):
        protocol.connection_made(Mock())
        return None, protocol

    create_serial_connection.side_effect = on_connection_made

    await client.connect()
    assert client.device_info == protocol.expected_device_info
    assert client.is_sleeping() is False


@pytest.mark.parametrize("protocol_fixture", ["protocol_1_61_1", "protocol_older"])
async def test_connect(protocol_fixture, request, create_serial_connection):
    protocol = request.getfixturevalue(protocol_fixture)
    client = Nextion("/dev/ttyS1", 9600, None)
    await connect_and_test(client, protocol, create_serial_connection)


async def test_failed_baud_probe_closes_before_next_attempt():
    client = Nextion("/dev/ttyS1", 9600)
    first = Mock(wait_connection=AsyncMock(), close=AsyncMock())
    second = Mock(wait_connection=AsyncMock(), close=AsyncMock())
    client._get_priority_ordered_baud_rates = Mock(return_value=[9600, 19200])

    async def create_connection(baud):
        if baud == 19200:
            first.close.assert_awaited_once()
            return second
        return first

    client._create_serial_connection = AsyncMock(side_effect=create_connection)
    client._read_packet = AsyncMock(return_value=b"")
    client._attempt_connect_messages = AsyncMock(
        side_effect=[NoValidReply("bad reply"), None]
    )
    with patch("nextion.client.asyncio.sleep", new_callable=AsyncMock):
        await client._try_connect_on_different_baudrates()

    assert client._connection is second
    assert client._baud_rate == 19200
    second.close.assert_not_awaited()


@pytest.mark.parametrize(
    "error", [CommandTimeout("sleep timeout"), asyncio.CancelledError()]
)
async def test_connect_closes_connection_when_initialization_fails(error):
    client = Nextion("/dev/ttyS1", 9600)
    connection = Mock(close=AsyncMock())

    async def establish_connection():
        client._connection = connection
        client.device_info = DeviceInfo(
            "address", "model", "version", "serial", "flash"
        )

    client._try_connect_on_different_baudrates = AsyncMock(
        side_effect=establish_connection
    )
    client._command = AsyncMock(side_effect=[True, error])
    with pytest.raises(type(error)):
        await client.connect()

    assert client._command.await_args_list == [
        call("bkcmd=3", attempts=1),
        call("get sleep", attempts=1),
    ]
    connection.close.assert_awaited_once()
    assert client._connection is None


async def test_cancelled_baud_probe_closes_connection():
    client = Nextion("/dev/ttyS1", 9600)
    connection = Mock(
        wait_connection=AsyncMock(side_effect=asyncio.CancelledError), close=AsyncMock()
    )
    client._create_serial_connection = AsyncMock(return_value=connection)
    with pytest.raises(asyncio.CancelledError):
        await client._connect_at_baud(9600)
    connection.close.assert_awaited_once()
    assert client._connection is None


@pytest.mark.parametrize("bad_reply", [b"comok short", b"comok \xff"])
async def test_malformed_connect_reply_tries_broadcast(bad_reply):
    client = Nextion("/dev/ttyS1", 9600)
    client._write_command_raw = Mock()
    client._read_packet = AsyncMock(
        side_effect=[bad_reply, b"comok 1,67-0,model,130,61488,serial,16777216"]
    )
    await client._attempt_connect_messages(0.1)
    assert client._write_command_raw.call_args_list == [
        call(b"connect"),
        call(b"\xff\xffconnect"),
    ]
    assert client.device_info == DeviceInfo(
        "67-0", "model", "130", "serial", "16777216"
    )
