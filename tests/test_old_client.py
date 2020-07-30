import binascii
import logging

import asynctest

from nextion import Nextion
from nextion.protocol import BasicProtocol
from tests.decorators import with_client, with_protocol

logger = logging.getLogger("nextion").getChild(__name__)


class DummyOldNextionProtocol(BasicProtocol):
    def write(self, data: bytes, eol=True):
        logger.debug(f"sent: {data}")
        if data == b"DRAKJHSUYDGBNCJHGJKSHBDN":
            self.data_received(b"\x1a")
        elif data == b"connect":
            self.data_received(
                binascii.unhexlify(
                    "636f6d6f6b20312c36372d302c4e5834383237543034335f303131522c3133302c36313438382c453436383543423335423631333633362c3136373737323136"
                )
            )
        elif data == b"bkcmd=3":
            self.data_received(b"\x01")
        elif data == b"thup=1":
            self.data_received(b"\x01")
        elif data == b"get sleep":
            self.data_received(b"\x71\x00\x00\x00\x00")
            self.data_received(b"\x01")
        else:
            logger.error(f"write with no response(eol={eol}): {data}")


class TestClientPrior1_61_1(asynctest.TestCase):
    @with_protocol(protocol_class=DummyOldNextionProtocol)
    async def test_connect(self, client: Nextion, protocol):
        await client.connect()
        assert client.is_sleeping() is False

    @with_client
    async def test_get_numeric(self, client: Nextion, protocol):
        client._connection = protocol

        response_data = binascii.unhexlify("7101000000")

        protocol.read = asynctest.CoroutineMock(
            side_effect=[response_data, b"\01", b""]
        )

        result = await client.get("sleep")
        protocol.write.assert_called_once_with(b"get sleep")

        assert result == 1

    @with_client
    async def test_get_string(self, client: Nextion, protocol):
        client._connection = protocol

        response_data = binascii.unhexlify("703430")

        protocol.read = asynctest.CoroutineMock(
            side_effect=[response_data, b"\01", b""]
        )

        result = await client.get("t16.txt")
        protocol.write.assert_called_once_with(b"get t16.txt")

        assert result == "40"

    @with_client
    async def test_set(self, client: Nextion, protocol):
        client._connection = protocol

        protocol.read = asynctest.CoroutineMock(side_effect=[b"\01", b""])

        result = await client.set("sleep", 1)
        protocol.write.assert_called_once_with(b"sleep=1")

        assert result is True
