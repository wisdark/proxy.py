# -*- coding: utf-8 -*-
"""
    proxy.py
    ~~~~~~~~
    ⚡⚡⚡ Fast, Lightweight, Pluggable, TLS interception capable proxy server focused on
    Network monitoring, controls & Application development, testing, debugging.

    :copyright: (c) 2013-present by Abhinav Singh and contributors.
    :license: BSD, see LICENSE for more details.
"""
import socket
import logging
import ipaddress
from typing import Any, Union, Optional

from .base import BaseListener
from ...common.flag import flags
from ...common.constants import (
    DEFAULT_PORT, DEFAULT_PORT_FILE, DEFAULT_IPV4_HOSTNAME,
)


flags.add_argument(
    '--hostname',
    type=str,
    default=str(DEFAULT_IPV4_HOSTNAME),
    help='Default: 127.0.0.1. Server IP address.',
)

flags.add_argument(
    '--hostnames',
    action='append',
    nargs='+',
    type=str,
    default=None,
    help='Default: None.  Additional IP addresses to listen on.',
)

flags.add_argument(
    '--port',
    type=int,
    default=DEFAULT_PORT,
    help='Default: 8899.  Server port.  To listen on more ports, pass them using --ports flag.',
)

flags.add_argument(
    '--ports',
    action='append',
    nargs='+',
    type=int,
    default=None,
    help='Default: None.  Additional ports to listen on.',
)

flags.add_argument(
    '--port-file',
    type=str,
    default=DEFAULT_PORT_FILE,
    help='Default: None. Save server port numbers. Useful when using --port=0 ephemeral mode.',
)

logger = logging.getLogger(__name__)


class TcpSocketListener(BaseListener):
    """Tcp listener."""

    def __init__(
        self,
        hostname: Union[ipaddress.IPv4Address, ipaddress.IPv6Address],
        port: int,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self.hostname = hostname
        self.port = port
        # Set after binding to a port.
        #
        # Stored here separately for ephemeral port discovery.
        self._port: Optional[int] = None
        super().__init__(*args, **kwargs)

    def listen(self) -> socket.socket:
        sock = socket.socket(
            socket.AF_INET6 if self.hostname.version == 6 else socket.AF_INET,
            socket.SOCK_STREAM,
        )
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # s.setsockopt(socket.SOL_TCP, socket.TCP_FASTOPEN, 5)
        sock.bind((str(self.hostname), self.port))
        sock.listen(self.flags.backlog)
        sock.setblocking(False)
        self._port = sock.getsockname()[1]
        logger.debug(
            'Listening on %s:%s' % (self.hostname, self._port),
        )
        return sock
