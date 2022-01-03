import binascii
import typing
from abc import ABC, abstractmethod

import asynctest

from nextion import Nextion
from tests.decorators import with_client


class AbstractTestClient(ABC):
    @with_client
    async def setUp(self, client: Nextion, protocol):
        self.client = client
        self.protocol = protocol

    @abstractmethod
    async def _get_mocked_result(
        self,
        response_data,
        action_fn: typing.Callable[[Nextion], typing.Any],
        asset_command_called,
    ):
        pass

    async def test_get_numeric(self):
        result = await self._get_mocked_result(
            "7101000000", lambda client: client.get("sleep"), "get sleep"
        )

        assert result == 1

    async def test_get_negative_numeric(self):
        result = await self._get_mocked_result(
            "71a5ffffff", lambda client: client.get("var1"), "get var1"
        )

        assert result == -91

    async def test_get_string(self):
        result = await self._get_mocked_result(
            "703430", lambda client: client.get("t16.txt"), "get t16.txt"
        )

        assert result == "40"

    async def test_sendme_pageid(self):
        result = await self._get_mocked_result(
            "6605", lambda client: client.command("sendme"), "sendme"
        )

        print(result)
        assert result == 5

    async def test_set(self):
        result = await self._get_mocked_result(
            b"\x01", lambda client: client.set("sleep", 1), "sleep=1"
        )

        assert result is True


class TestClientAfter1_61_1(AbstractTestClient, asynctest.TestCase):
    async def _get_mocked_result(
        self,
        response_data,
        action_fn: typing.Callable[[Nextion], typing.Any],
        asset_command_called,
    ):
        if isinstance(response_data, str):
            response_data = binascii.unhexlify(response_data)
        if isinstance(asset_command_called, str):
            asset_command_called = asset_command_called.encode()

        self.protocol.read = asynctest.CoroutineMock(side_effect=[response_data])
        result = await action_fn(self.client)  # self.client.get(variable)
        self.protocol.write.assert_called_once_with(asset_command_called)
        return result


class TestClientPrior1_61_1(AbstractTestClient, asynctest.TestCase):
    async def _get_mocked_result(
        self,
        response_data,
        action_fn: typing.Callable[[Nextion], typing.Any],
        asset_command_called,
    ):
        if isinstance(response_data, str):
            response_data = binascii.unhexlify(response_data)
        if isinstance(asset_command_called, str):
            asset_command_called = asset_command_called.encode()

        self.protocol.read = asynctest.CoroutineMock(
            side_effect=[response_data, b"\01", b""]
        )
        result = await action_fn(self.client)  # self.client.get(variable)
        self.protocol.write.assert_called_once_with(asset_command_called)
        return result
