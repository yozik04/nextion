import binascii
import logging

import asynctest

from nextion import Nextion
from nextion.protocol import BasicProtocol
from tests.decorators import with_protocol

logger = logging.getLogger("nextion").getChild(__name__)


class DummyNextionProtocol_1_61_1(BasicProtocol):
    def write(self, data: bytes, eol=True):
        logger.debug("sent: %s" % (data))
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
        elif data == b"get sleep":
            self.data_received(b"\x71\x00\x00\x00\x00")
        else:
            logger.error("write with no response(eol=%s): %s" % (eol, data))


class DummyOldNextionProtocol(BasicProtocol):
    def write(self, data: bytes, eol=True):
        logger.debug("sent: %s" % (data))
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
            logger.error("write with no response(eol=%s): %s" % (eol, data))


class TestClientConnection(asynctest.TestCase):
    @with_protocol(protocol_class=DummyNextionProtocol_1_61_1)
    async def test_connect_1_61_1_plus(self, client: Nextion, protocol):
        await client.connect()
        assert client.is_sleeping() is False

    @with_protocol(protocol_class=DummyOldNextionProtocol)
    async def test_connect_older_than_1_61_1(self, client: Nextion, protocol):
        await client.connect()
        assert client.is_sleeping() is False
