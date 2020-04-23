import logging
from unittest import TestCase
from unittest.mock import MagicMock

from nextion.protocol import NextionProtocol

logging.basicConfig(level=logging.DEBUG)


class TestClient(TestCase):
    def test_data_received(self):
        obj = NextionProtocol(MagicMock())

        obj.data_received(b"p12\xff\xff\xff\x01\xff\xff\xff\xff\xff\xff")

        self.assertEqual(3, obj.queue.qsize())

        self.assertEqual(b"p12", obj.read_no_wait())
        self.assertEqual(b"\x01", obj.read_no_wait())
        self.assertEqual(b"", obj.read_no_wait())

    def test_data_received_chunked(self):
        obj = NextionProtocol(MagicMock())

        obj.data_received(b"p12\xff\xff")
        obj.data_received(b"\xff\x01\xff")
        obj.data_received(b"\xff\xff")
        obj.data_received(b"\xff\xff\xff")

        self.assertEqual(3, obj.queue.qsize())

        self.assertEqual(b"p12", obj.read_no_wait())
        self.assertEqual(b"\x01", obj.read_no_wait())
        self.assertEqual(b"", obj.read_no_wait())
