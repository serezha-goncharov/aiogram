import copy
from typing import AsyncContextManager

import aiohttp
import pytest
from aresponses import ResponsesMockServer

from aiogram.api.client.session.aiohttp import AiohttpSession
from aiogram.api.methods import Request, TelegramMethod
from aiogram.api.types import InputFile

try:
    from asynctest import CoroutineMock, patch
except ImportError:
    from unittest.mock import AsyncMock as CoroutineMock, patch  # type: ignore


class BareInputFile(InputFile):
    async def read(self, chunk_size: int):
        yield b""


class TestAiohttpSession:
    @pytest.mark.asyncio
    async def test_create_session(self):
        session = AiohttpSession()

        assert session._session is None
        aiohttp_session = await session.create_session()
        assert session._session is not None
        assert isinstance(aiohttp_session, aiohttp.ClientSession)

    @pytest.mark.asyncio
    async def test_close_session(self):
        session = AiohttpSession()
        await session.create_session()

        with patch("aiohttp.ClientSession.close", new=CoroutineMock()) as mocked_close:
            await session.close()
            mocked_close.assert_called_once()

    def test_build_form_data_with_data_only(self):
        request = Request(
            method="method",
            data={
                "str": "value",
                "int": 42,
                "bool": True,
                "null": None,
                "list": ["foo"],
                "dict": {"bar": "baz"},
            },
        )

        session = AiohttpSession()
        form = session.build_form_data(request)

        fields = form._fields
        assert len(fields) == 5
        assert all(isinstance(field[2], str) for field in fields)
        assert "null" not in [item[0]["name"] for item in fields]

    def test_build_form_data_with_files(self):
        request = Request(
            method="method",
            data={"key": "value"},
            files={"document": BareInputFile(filename="file.txt")},
        )

        session = AiohttpSession()
        form = session.build_form_data(request)

        fields = form._fields

        assert len(fields) == 2
        assert fields[1][0]["name"] == "document"
        assert fields[1][0]["filename"] == "file.txt"
        assert isinstance(fields[1][2], BareInputFile)

    @pytest.mark.asyncio
    async def test_make_request(self, aresponses: ResponsesMockServer):
        aresponses.add(
            aresponses.ANY,
            "/bot42:TEST/method",
            "post",
            aresponses.Response(
                status=200,
                text='{"ok": true, "result": 42}',
                headers={"Content-Type": "application/json"},
            ),
        )

        session = AiohttpSession()

        class TestMethod(TelegramMethod[int]):
            __returning__ = int

            def build_request(self) -> Request:
                return Request(method="method", data={})

        call = TestMethod()
        with patch(
            "aiogram.api.client.session.base.BaseSession.raise_for_status"
        ) as patched_raise_for_status:
            result = await session.make_request("42:TEST", call)
            assert isinstance(result, int)
            assert result == 42

            assert patched_raise_for_status.called_once()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        session = AiohttpSession()
        assert isinstance(session, AsyncContextManager)

        with patch(
            "aiogram.api.client.session.aiohttp.AiohttpSession.create_session",
            new_callable=CoroutineMock,
        ) as mocked_create_session, patch(
            "aiogram.api.client.session.aiohttp.AiohttpSession.close", new_callable=CoroutineMock
        ) as mocked_close:
            async with session as ctx:
                assert session == ctx
            mocked_close.awaited_once()
            mocked_create_session.awaited_once()

    @pytest.mark.asyncio
    async def test_deepcopy(self):
        # Session should be copied without aiohttp.ClientSession
        async with AiohttpSession() as session:
            cloned_session = copy.deepcopy(session)
            assert cloned_session != session
            assert cloned_session._session is None