import binascii
import logging
from unittest.mock import Mock, patch

import pytest

from nextion import Nextion
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
            logger.error(f"write with no response(eol={eol}): {data}")


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
        super().__init__(responses, *args, **kwargs)


@pytest.fixture
def transport():
    return Mock()


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


async def connect_and_test(client, protocol, transport, create_serial_connection):
    async def on_connection_made(*args, **kwargs):
        protocol.connection_made(transport)
        return None, protocol

    create_serial_connection.side_effect = on_connection_made

    await client.connect()
    assert client.is_sleeping() is False


@pytest.mark.parametrize("protocol_fixture", ["protocol_1_61_1", "protocol_older"])
async def test_connect(protocol_fixture, request, transport, create_serial_connection):
    protocol = request.getfixturevalue(protocol_fixture)
    client = Nextion("/dev/ttyS1", 9600, None)
    await connect_and_test(client, protocol, transport, create_serial_connection)
