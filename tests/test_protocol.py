import typing
from unittest import TestCase
from unittest.mock import MagicMock

from nextion.protocol import NextionProtocol


class TestClient(TestCase):
    def assertPacketsParsed(
        self, input_chunks: typing.List[bytes], expected_packets: typing.List[bytes]
    ):
        obj = NextionProtocol(MagicMock())

        for chunk in input_chunks:
            obj.data_received(chunk)

        self.assertEqual(len(expected_packets), obj.queue.qsize())

        for expected_packet in expected_packets:
            self.assertEqual(expected_packet, obj.read_no_wait())

    def test_one_chunk_data_received(self):
        self.assertPacketsParsed(
            [b"\x70\x31\x32\xff\xff\xff\x01\xff\xff\xff\xff\xff\xff"],
            [b"\x70\x31\x32", b"\x01", b""],
        )

    def test_chunked_data_received(self):
        self.assertPacketsParsed(
            [b"\x70\x31\x32\xff\xff", b"\xff\x01\xff", b"\xff\xff", b"\xff\xff\xff"],
            [b"\x70\x31\x32", b"\x01", b""],
        )

    def test_negative_integer_data_received(self):
        self.assertPacketsParsed(
            [b"\x71\xa5\xff\xff\xff\xff\xff\xff\x01\xff\xff\xff\xff\xff\xff"],
            [b"\x71\xa5\xff\xff\xff", b"\x01", b""],
        )

    def test_negative_integer_chunked_data_received(self):
        self.assertPacketsParsed(
            [
                b"\x71\xa5\xff",
                b"\xff\xff\xff",
                b"\xff\xff\x01",
                b"\xff\xff",
                b"\xff\xff\xff\xff",
            ],
            [b"\x71\xa5\xff\xff\xff", b"\x01", b""],
        )

    def test_junk_data_received(self):
        self.assertPacketsParsed(
            [b"\x71\xff\xff\xff\x71\xa5\xff\xff\xff\xff\xff\xff"],
            [b"\x71\xa5\xff\xff\xff"],
        )
