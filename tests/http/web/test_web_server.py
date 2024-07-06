# -*- coding: utf-8 -*-
"""
    proxy.py
    ~~~~~~~~
    ⚡⚡⚡ Fast, Lightweight, Pluggable, TLS interception capable proxy server focused on
    Network monitoring, controls & Application development, testing, debugging.

    :copyright: (c) 2013-present by Abhinav Singh and contributors.
    :license: BSD, see LICENSE for more details.
"""
import os
import gzip
import tempfile
import selectors
from typing import Any

import pytest

from pytest_mock import MockerFixture

from proxy.http import HttpProtocolHandler, HttpClientConnection
from proxy.common.flag import FlagParser
from proxy.http.parser import HttpParser, httpParserTypes, httpParserStates
from proxy.common.utils import bytes_, build_http_request, build_http_response
from proxy.common.plugins import Plugins
from proxy.http.responses import NOT_FOUND_RESPONSE_PKT
from proxy.common.constants import (
    CRLF, PROXY_PY_DIR, PLUGIN_PAC_FILE, PLUGIN_HTTP_PROXY, PLUGIN_WEB_SERVER,
)
from ...test_assertions import Assertions


PAC_FILE_PATH = os.path.join(
    os.path.dirname(PROXY_PY_DIR),
    'helper',
    'proxy.pac',
)

PAC_FILE_CONTENT = b'function FindProxyForURL(url, host) { return "PROXY localhost:8899; DIRECT"; }'


def test_on_client_connection_called_on_teardown(mocker: MockerFixture) -> None:
    plugin = mocker.MagicMock()
    mock_socket_dup = mocker.patch('socket.dup')
    mock_socket_dup.side_effect = lambda fd: fd
    flags = FlagParser.initialize(threaded=True)
    flags.plugins = {b'HttpProtocolHandlerPlugin': [plugin]}
    _conn = mocker.MagicMock()
    _addr = ('127.0.0.1', 54382)
    protocol_handler = HttpProtocolHandler(
        HttpClientConnection(_conn, _addr),
        flags=flags,
    )
    protocol_handler.initialize()
    plugin.assert_not_called()
    mock_run_once = mocker.patch.object(protocol_handler, '_run_once')
    mock_run_once.return_value = True
    protocol_handler.run()
    assert _conn.closed


def mock_selector_for_client_read(self: Any) -> None:
    self.mock_selector.return_value.select.return_value = [
        (
            selectors.SelectorKey(
                fileobj=self._conn.fileno(),
                fd=self._conn.fileno(),
                events=selectors.EVENT_READ,
                data=None,
            ),
            selectors.EVENT_READ,
        ),
    ]

# @mock.patch('socket.fromfd')
# def test_on_client_connection_called_on_teardown(
#         self, mock_fromfd: mock.Mock,
# ) -> None:
#     flags = FlagParser.initialize(threaded=True)
#     plugin = mock.MagicMock()
#     flags.plugins = {b'HttpProtocolHandlerPlugin': [plugin]}
#     self._conn = mock_fromfd.return_value
#     self.protocol_handler = HttpProtocolHandler(
#         HttpClientConnection(self._conn, self._addr),
#         flags=flags,
#     )
#     self.protocol_handler.initialize()
#     plugin.assert_called()
#     with mock.patch.object(self.protocol_handler, '_run_once') as mock_run_once:
#         mock_run_once.return_value = True
#         self.protocol_handler.run()
#     self.assertTrue(self._conn.closed)
#     plugin.return_value.on_client_connection_close.assert_called()

# @mock.patch('socket.fromfd')
# def test_on_client_connection_called_on_teardown(
#         self, mock_fromfd: mock.Mock,
# ) -> None:
#     flags = FlagParser.initialize(threaded=True)
#     plugin = mock.MagicMock()
#     flags.plugins = {b'HttpProtocolHandlerPlugin': [plugin]}
#     self._conn = mock_fromfd.return_value
#     self.protocol_handler = HttpProtocolHandler(
#         HttpClientConnection(self._conn, self._addr),
#         flags=flags,
#     )
#     self.protocol_handler.initialize()
#     plugin.assert_called()
#     with mock.patch.object(self.protocol_handler, '_run_once') as mock_run_once:
#         mock_run_once.return_value = True
#         self.protocol_handler.run()
#     self.assertTrue(self._conn.closed)
#     plugin.return_value.on_client_connection_close.assert_called()

# @mock.patch('socket.fromfd')
# def test_on_client_connection_called_on_teardown(
#         self, mock_fromfd: mock.Mock,
# ) -> None:
#     flags = FlagParser.initialize(threaded=True)
#     plugin = mock.MagicMock()
#     flags.plugins = {b'HttpProtocolHandlerPlugin': [plugin]}
#     self._conn = mock_fromfd.return_value
#     self.protocol_handler = HttpProtocolHandler(
#         HttpClientConnection(self._conn, self._addr),
#         flags=flags,
#     )
#     self.protocol_handler.initialize()
#     plugin.assert_called()
#     with mock.patch.object(self.protocol_handler, '_run_once') as mock_run_once:
#         mock_run_once.return_value = True
#         self.protocol_handler.run()
#     self.assertTrue(self._conn.closed)
#     plugin.return_value.on_client_connection_close.assert_called()


class TestWebServerPluginWithPacFilePlugin(Assertions):

    @pytest.fixture(
        autouse=True, params=[
            PAC_FILE_PATH,
            PAC_FILE_CONTENT,
        ],
    )  # type: ignore[misc]
    def _setUp(self, request: Any, mocker: MockerFixture) -> None:
        self.mock_socket = mocker.patch('socket.socket')
        self.mock_socket_dup = mocker.patch('socket.dup', side_effect=lambda fd: fd)
        self.mock_selector = mocker.patch('selectors.DefaultSelector')
        self.fileno = 10
        self._addr = ('127.0.0.1', 54382)
        self._conn = self.mock_socket.return_value
        self.pac_file = request.param
        if isinstance(self.pac_file, str):
            with open(self.pac_file, 'rb') as f:
                self.expected_response = f.read()
        else:
            self.expected_response = PAC_FILE_CONTENT
        self.flags = FlagParser.initialize(
            pac_file=self.pac_file, threaded=True,
        )
        self.flags.plugins = Plugins.load([
            bytes_(PLUGIN_HTTP_PROXY),
            bytes_(PLUGIN_WEB_SERVER),
            bytes_(PLUGIN_PAC_FILE),
        ])
        self.protocol_handler = HttpProtocolHandler(
            HttpClientConnection(self._conn, self._addr),
            flags=self.flags,
        )
        self.protocol_handler.initialize()
        self._conn.recv.return_value = CRLF.join([
            b'GET / HTTP/1.1',
            CRLF,
        ])
        mock_selector_for_client_read(self)

    @pytest.mark.asyncio    # type: ignore[misc]
    async def test_pac_file_served_from_disk(self) -> None:
        await self.protocol_handler._run_once()
        self.assertEqual(
            self.protocol_handler.request.state,
            httpParserStates.COMPLETE,
        )
        self._conn.send.called_once_with(
            build_http_response(
                200,
                reason=b'OK',
                headers={
                    b'Content-Type': b'application/x-ns-proxy-autoconfig',
                },
                body=self.expected_response,
                conn_close=True,
            ),
        )


class TestStaticWebServerPlugin(Assertions):

    @pytest.fixture(autouse=True)   # type: ignore[misc]
    def _setUp(self, mocker: MockerFixture) -> None:
        self.mock_socket = mocker.patch('socket.socket')
        self.mock_socket_dup = mocker.patch('socket.dup', side_effect=lambda fd: fd)
        self.mock_selector = mocker.patch('selectors.DefaultSelector')
        self.fileno = 10
        self._addr = ('127.0.0.1', 54382)
        self._conn = self.mock_socket.return_value
        # Setup a static directory
        self.static_server_dir = os.path.join(tempfile.gettempdir(), 'static')
        self.index_file_path = os.path.join(
            self.static_server_dir, 'index.html',
        )
        self.html_file_content = b'''<html><head></head><body><h1>Proxy.py Testing</h1></body></html>'''
        os.makedirs(self.static_server_dir, exist_ok=True)
        with open(self.index_file_path, 'wb') as f:
            f.write(self.html_file_content)
        #
        flags = FlagParser.initialize(
            enable_static_server=True,
            static_server_dir=self.static_server_dir,
            threaded=True,
        )
        flags.plugins = Plugins.load([
            bytes_(PLUGIN_HTTP_PROXY),
            bytes_(PLUGIN_WEB_SERVER),
        ])
        self.protocol_handler = HttpProtocolHandler(
            HttpClientConnection(self._conn, self._addr),
            flags=flags,
        )
        self.protocol_handler.initialize()

    @pytest.mark.asyncio    # type: ignore[misc]
    async def test_static_web_server_serves(self) -> None:
        self._conn.recv.return_value = build_http_request(
            b'GET', b'/index.html',
        )
        self.mock_selector.return_value.select.side_effect = [
            [(
                selectors.SelectorKey(
                    fileobj=self._conn.fileno(),
                    fd=self._conn.fileno(),
                    events=selectors.EVENT_READ,
                    data=None,
                ),
                selectors.EVENT_READ,
            )],
            [(
                selectors.SelectorKey(
                    fileobj=self._conn.fileno(),
                    fd=self._conn.fileno(),
                    events=selectors.EVENT_WRITE,
                    data=None,
                ),
                selectors.EVENT_WRITE,
            )],
        ]
        await self.protocol_handler._run_once()
        await self.protocol_handler._run_once()

        self.assertEqual(self.mock_selector.return_value.select.call_count, 2)
        self.assertEqual(self._conn.send.call_count, 1)
        encoded_html_file_content = gzip.compress(self.html_file_content)

        # parse response and verify
        response = HttpParser(httpParserTypes.RESPONSE_PARSER)
        response.parse(self._conn.send.call_args[0][0])
        self.assertEqual(response.code, b'200')
        self.assertEqual(response.header(b'content-type'), b'text/html')
        self.assertEqual(response.header(b'cache-control'), b'max-age=86400')
        self.assertEqual(response.header(b'content-encoding'), b'gzip')
        self.assertEqual(response.header(b'connection'), b'close')
        self.assertEqual(
            response.header(b'content-length'),
            bytes_(len(encoded_html_file_content)),
        )
        assert response.body
        self.assertEqual(
            gzip.decompress(response.body),
            self.html_file_content,
        )

    @pytest.mark.asyncio    # type: ignore[misc]
    async def test_static_web_server_serves_404(self) -> None:
        self._conn.recv.return_value = build_http_request(
            b'GET', b'/not-found.html',
        )
        self.mock_selector.return_value.select.side_effect = [
            [(
                selectors.SelectorKey(
                    fileobj=self._conn.fileno(),
                    fd=self._conn.fileno(),
                    events=selectors.EVENT_READ,
                    data=None,
                ),
                selectors.EVENT_READ,
            )],
            [(
                selectors.SelectorKey(
                    fileobj=self._conn.fileno(),
                    fd=self._conn.fileno(),
                    events=selectors.EVENT_WRITE,
                    data=None,
                ),
                selectors.EVENT_WRITE,
            )],
        ]

        await self.protocol_handler._run_once()
        await self.protocol_handler._run_once()

        self.assertEqual(self.mock_selector.return_value.select.call_count, 2)
        self.assertEqual(self._conn.send.call_count, 1)
        self.assertEqual(
            self._conn.send.call_args[0][0],
            NOT_FOUND_RESPONSE_PKT,
        )


class TestWebServerPlugin(Assertions):

    @pytest.fixture(autouse=True)   # type: ignore[misc]
    def _setUp(self, mocker: MockerFixture) -> None:
        self.mock_socket = mocker.patch('socket.socket')
        self.mock_socket_dup = mocker.patch('socket.dup', side_effect=lambda fd: fd)
        self.mock_selector = mocker.patch('selectors.DefaultSelector')
        self.fileno = 10
        self._addr = ('127.0.0.1', 54382)
        self._conn = self.mock_socket.return_value
        self.flags = FlagParser.initialize(threaded=True)
        self.flags.plugins = Plugins.load([
            bytes_(PLUGIN_HTTP_PROXY),
            bytes_(PLUGIN_WEB_SERVER),
        ])
        self.protocol_handler = HttpProtocolHandler(
            HttpClientConnection(self._conn, self._addr),
            flags=self.flags,
        )
        self.protocol_handler.initialize()

    @pytest.mark.asyncio    # type: ignore[misc]
    async def test_default_web_server_returns_404(self) -> None:
        self._conn = self.mock_socket.return_value
        self.mock_selector.return_value.select.return_value = [
            (
                selectors.SelectorKey(
                    fileobj=self._conn.fileno(),
                    fd=self._conn.fileno(),
                    events=selectors.EVENT_READ,
                    data=None,
                ),
                selectors.EVENT_READ,
            ),
        ]
        flags = FlagParser.initialize(threaded=True)
        flags.plugins = Plugins.load([
            bytes_(PLUGIN_HTTP_PROXY),
            bytes_(PLUGIN_WEB_SERVER),
        ])
        self.protocol_handler = HttpProtocolHandler(
            HttpClientConnection(self._conn, self._addr),
            flags=flags,
        )
        self.protocol_handler.initialize()
        self._conn.recv.return_value = CRLF.join([
            b'GET /hello HTTP/1.1',
            CRLF,
        ])
        await self.protocol_handler._run_once()
        self.assertEqual(
            self.protocol_handler.request.state,
            httpParserStates.COMPLETE,
        )
        self.assertEqual(
            self.protocol_handler.work.buffer[0],
            NOT_FOUND_RESPONSE_PKT,
        )
