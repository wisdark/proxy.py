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
import sys
import gzip
import json
import time
import pprint
import signal
import socket
import getpass
import logging
import argparse
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Type, Tuple, Optional, cast

from .core.ssh import SshTunnelListener, SshHttpProtocolHandler
from .core.work import ThreadlessPool
from .core.event import EventManager
from .http.codes import httpStatusCodes
from .common.flag import FlagParser, flags
from .http.client import client
from .common.types import HostPort
from .common.utils import bytes_
from .core.work.fd import RemoteFdExecutor
from .http.methods import httpMethods
from .core.acceptor import AcceptorPool
from .core.listener import ListenerPool
from .core.ssh.base import BaseSshTunnelListener
from .common.plugins import Plugins
from .common.version import __version__
from .common.constants import (
    IS_WINDOWS, HTTPS_PROTO, DEFAULT_PLUGINS, DEFAULT_VERSION,
    DEFAULT_LOG_FILE, DEFAULT_PID_FILE, DEFAULT_LOG_LEVEL, DEFAULT_BASIC_AUTH,
    DEFAULT_LOG_FORMAT, DEFAULT_WORK_KLASS, DEFAULT_OPEN_FILE_LIMIT,
    DEFAULT_ENABLE_DASHBOARD, DEFAULT_ENABLE_SSH_TUNNEL,
    DEFAULT_SSH_LISTENER_KLASS,
)
from .core.event.metrics import MetricsEventSubscriber
from .http.parser.parser import HttpParser


if TYPE_CHECKING:   # pragma: no cover
    from .core.listener import TcpSocketListener
    from .core.ssh.base import BaseSshTunnelHandler


logger = logging.getLogger(__name__)


flags.add_argument(
    '--version',
    '-v',
    action='store_true',
    default=DEFAULT_VERSION,
    help='Prints proxy.py version.',
)

# TODO: Add --verbose option which also
# starts to log traffic flowing between
# clients and upstream servers.
flags.add_argument(
    '--log-level',
    type=str,
    default=DEFAULT_LOG_LEVEL,
    help='Valid options: DEBUG, INFO (default), WARNING, ERROR, CRITICAL. '
    'Both upper and lowercase values are allowed. '
    'You may also simply use the leading character e.g. --log-level d',
)

flags.add_argument(
    '--log-file',
    type=str,
    default=DEFAULT_LOG_FILE,
    help='Default: sys.stdout. Log file destination.',
)

flags.add_argument(
    '--log-format',
    type=str,
    default=DEFAULT_LOG_FORMAT,
    help='Log format for Python logger.',
)

flags.add_argument(
    '--open-file-limit',
    type=int,
    default=DEFAULT_OPEN_FILE_LIMIT,
    help='Default: 1024. Maximum number of files (TCP connections) '
    'that proxy.py can open concurrently.',
)

flags.add_argument(
    '--plugins',
    action='append',
    nargs='+',
    default=DEFAULT_PLUGINS,
    help='Comma separated plugins.  ' +
    'You may use --plugins flag multiple times.',
)

# TODO: Ideally all `--enable-*` flags must be at the top-level.
# --enable-dashboard is specially needed here because
# ProxyDashboard class is not imported anywhere.
#
# Due to which, if we move this flag definition within dashboard
# plugin, users will have to explicitly enable dashboard plugin
# to also use flags provided by it.
flags.add_argument(
    '--enable-dashboard',
    action='store_true',
    default=DEFAULT_ENABLE_DASHBOARD,
    help='Default: False.  Enables proxy.py dashboard.',
)

# NOTE: Same reason as mention above.
# Ideally this flag belongs to proxy auth plugin.
flags.add_argument(
    '--basic-auth',
    type=str,
    default=DEFAULT_BASIC_AUTH,
    help='Default: No authentication. Specify colon separated user:password '
    'to enable basic authentication.',
)

flags.add_argument(
    '--enable-ssh-tunnel',
    action='store_true',
    default=DEFAULT_ENABLE_SSH_TUNNEL,
    help='Default: False.  Enable SSH tunnel.',
)

flags.add_argument(
    '--work-klass',
    type=str,
    default=DEFAULT_WORK_KLASS,
    help='Default: ' + DEFAULT_WORK_KLASS +
    '.  Work klass to use for work execution.',
)

flags.add_argument(
    '--pid-file',
    type=str,
    default=DEFAULT_PID_FILE,
    help='Default: None. Save "parent" process ID to a file.',
)

flags.add_argument(
    '--openssl',
    type=str,
    default='openssl',
    help='Default: openssl. Path to openssl binary. ' +
    'By default, assumption is that openssl is in your PATH.',
)

flags.add_argument(
    '--data-dir',
    type=str,
    default=None,
    help='Default: ~/.proxypy. Path to proxypy data directory.',
)

flags.add_argument(
    '--ssh-listener-klass',
    type=str,
    default=DEFAULT_SSH_LISTENER_KLASS,
    help='Default: '
    + DEFAULT_SSH_LISTENER_KLASS
    + '.  An implementation of BaseSshTunnelListener',
)


class Proxy:
    """Proxy is a context manager to control proxy.py library core.

    By default, :class:`~proxy.core.pool.AcceptorPool` is started with
    :class:`~proxy.http.handler.HttpProtocolHandler` work class.
    By definition, it expects HTTP traffic to flow between clients and server.

    In ``--threadless`` mode and without ``--local-executor``,
    a :class:`~proxy.core.executors.ThreadlessPool` is also started.
    Executor pool receives newly accepted work by :class:`~proxy.core.acceptor.Acceptor`
    and creates an instance of work class for processing the received work.

    In ``--threadless`` mode and with ``--local-executor 0``,
    acceptors will start a companion thread to handle accepted
    client connections.

    Optionally, Proxy class also initializes the EventManager.
    A multi-process safe pubsub system which can be used to build various
    patterns for message sharing and/or signaling.
    """

    def __init__(self, input_args: Optional[List[str]] = None, **opts: Any) -> None:
        self.opts = opts
        self.flags = FlagParser.initialize(input_args, **opts)
        self.listeners: Optional[ListenerPool] = None
        self.executors: Optional[ThreadlessPool] = None
        self.acceptors: Optional[AcceptorPool] = None
        self.event_manager: Optional[EventManager] = None
        self.ssh_tunnel_listener: Optional[BaseSshTunnelListener] = None
        self.metrics_subscriber: Optional[MetricsEventSubscriber] = None

    def __enter__(self) -> 'Proxy':
        self.setup()
        return self

    def __exit__(self, *args: Any) -> None:
        self.shutdown()

    def setup(self) -> None:
        # TODO: Introduce cron feature
        # https://github.com/abhinavsingh/proxy.py/discussions/808
        #
        # TODO: Introduce ability to change flags dynamically
        # https://github.com/abhinavsingh/proxy.py/discussions/1020
        #
        # TODO: Python shell within running proxy.py environment
        # https://github.com/abhinavsingh/proxy.py/discussions/1021
        #
        self._write_pid_file()
        # We setup listeners first because of flags.port override
        # in case of ephemeral port being used
        self.listeners = ListenerPool(flags=self.flags)
        self.listeners.setup()
        # Override flags.port to match the actual port
        # we are listening upon.  This is necessary to preserve
        # the server port when `--port=0` is used.
        if not self.flags.unix_socket_path:
            self.flags.port = cast(
                'TcpSocketListener',
                self.listeners.pool[0],
            )._port
        # --ports flag can also use 0 as value for ephemeral port selection.
        # Here, we override flags.ports to reflect actual listening ports.
        ports = set()
        offset = 1 if self.flags.unix_socket_path else 0
        for index in range(offset, offset + len(self.flags.ports)):
            ports.add(
                cast(
                    'TcpSocketListener',
                    self.listeners.pool[index],
                )._port,
            )
        if self.flags.port in ports:
            ports.remove(self.flags.port)
        self.flags.ports = list(ports)
        # Write ports to port file
        self._write_port_file()
        # Setup EventManager
        if self.flags.enable_events:
            logger.info('Core Event enabled')
            self.event_manager = EventManager()
            self.event_manager.setup()
        event_queue = (
            self.event_manager.queue if self.event_manager is not None else None
        )
        # Setup remote executors only if
        # --local-executor mode isn't enabled.
        if self.remote_executors_enabled:
            self.executors = ThreadlessPool(
                flags=self.flags,
                event_queue=event_queue,
                executor_klass=RemoteFdExecutor,
            )
            self.executors.setup()
        # Setup acceptors
        self.acceptors = AcceptorPool(
            flags=self.flags,
            listeners=self.listeners,
            executor_queues=self.executors.work_queues if self.executors else [],
            executor_pids=self.executors.work_pids if self.executors else [],
            executor_locks=self.executors.work_locks if self.executors else [],
            event_queue=event_queue,
        )
        self.acceptors.setup()
        # Start SSH tunnel acceptor if enabled
        if self.flags.enable_ssh_tunnel:
            self.ssh_tunnel_listener = self._setup_tunnel(
                flags=self.flags,
                **self.opts,
            )
        if event_queue is not None and self.flags.enable_metrics:
            self.metrics_subscriber = MetricsEventSubscriber(
                event_queue,
                self.flags.metrics_lock,
            )
            self.metrics_subscriber.setup()
        # TODO: May be close listener fd as we don't need it now
        if threading.current_thread() == threading.main_thread():
            self._register_signals()

    @staticmethod
    def _setup_tunnel(
        flags: argparse.Namespace,
        ssh_handler_klass: Optional[Type['BaseSshTunnelHandler']] = None,
        ssh_listener_klass: Optional[Any] = None,
        **kwargs: Any,
    ) -> BaseSshTunnelListener:
        listener_klass = ssh_listener_klass or SshTunnelListener
        handler_klass = ssh_handler_klass or SshHttpProtocolHandler
        tunnel = cast(Type[BaseSshTunnelListener], listener_klass)(
            flags=flags,
            handler=handler_klass(flags=flags),
            **kwargs,
        )
        tunnel.setup()
        return tunnel

    def shutdown(self) -> None:
        if self.metrics_subscriber is not None:
            self.metrics_subscriber.shutdown()
        if self.flags.enable_ssh_tunnel:
            assert self.ssh_tunnel_listener is not None
            self.ssh_tunnel_listener.shutdown()
        assert self.acceptors
        self.acceptors.shutdown()
        if self.remote_executors_enabled:
            assert self.executors
            self.executors.shutdown()
        if self.flags.enable_events:
            assert self.event_manager is not None
            self.event_manager.shutdown()
        if self.listeners:
            self.listeners.shutdown()
            self._delete_port_file()
            self._delete_pid_file()

    @property
    def remote_executors_enabled(self) -> bool:
        return self.flags.threadless and \
            not self.flags.local_executor

    def _write_pid_file(self) -> None:
        if self.flags.pid_file:
            with open(self.flags.pid_file, 'wb') as pid_file:
                pid_file.write(bytes_(os.getpid()))

    def _delete_pid_file(self) -> None:
        if self.flags.pid_file \
                and os.path.exists(self.flags.pid_file):
            os.remove(self.flags.pid_file)

    def _write_port_file(self) -> None:
        if self.flags.port_file:
            with open(self.flags.port_file, 'wb') as port_file:
                if not self.flags.unix_socket_path:
                    port_file.write(bytes_(self.flags.port))
                    port_file.write(b'\n')
                for port in self.flags.ports:
                    port_file.write(bytes_(port))
                    port_file.write(b'\n')

    def _delete_port_file(self) -> None:
        if self.flags.port_file \
                and os.path.exists(self.flags.port_file):
            os.remove(self.flags.port_file)

    def _register_signals(self) -> None:
        # TODO: Define SIGUSR1, SIGUSR2
        signal.signal(signal.SIGINT, self._handle_exit_signal)
        signal.signal(signal.SIGTERM, self._handle_exit_signal)
        if not IS_WINDOWS:
            if hasattr(signal, 'SIGINFO'):
                signal.signal(      # pragma: no cover
                    signal.SIGINFO,       # pylint: disable=E1101
                    self._handle_siginfo,
                )
            signal.signal(signal.SIGHUP, self._handle_exit_signal)
            # TODO: SIGQUIT is ideally meant to terminate with core dumps
            signal.signal(signal.SIGQUIT, self._handle_exit_signal)

    @staticmethod
    def _handle_exit_signal(signum: int, _frame: Any) -> None:
        logger.debug('Received signal %d' % signum)
        sys.exit(0)

    def _handle_siginfo(self, _signum: int, _frame: Any) -> None:
        pprint.pprint(self.flags.__dict__)  # pragma: no cover


def sleep_loop(p: Optional[Proxy] = None) -> None:
    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break


def main(**opts: Any) -> None:
    with Proxy(sys.argv[1:], **opts) as p:
        sleep_loop(p)


def entry_point() -> None:
    main()


def grout() -> None:  # noqa: C901
    default_grout_tld = os.environ.get('JAXL_DEFAULT_GROUT_TLD', 'jaxl.io')

    def _clear_line() -> None:
        print('\r' + ' ' * 60, end='', flush=True)

    def _env(scheme: bytes, host: bytes, port: int) -> Optional[Dict[str, Any]]:
        try:
            response = client(
                scheme=scheme,
                host=host,
                port=port,
                path=b'/env/',
                method=httpMethods.BIND,
                body='v={0}&u={1}&h={2}'.format(
                    __version__,
                    os.environ.get('USER', getpass.getuser()),
                    socket.gethostname(),
                ).encode(),
            )
        except socket.gaierror:
            _clear_line()
            print(
                '\r\033[91mUnable to resolve\033[0m',
                end='',
                flush=True,
            )
            return None
        if response:
            if (
                response.code is not None
                and int(response.code) == httpStatusCodes.OK
                and response.body is not None
            ):
                return cast(
                    Dict[str, Any],
                    json.loads(
                        (
                            gzip.decompress(response.body).decode()
                            if response.has_header(b'content-encoding')
                            and response.header(b'content-encoding') == b'gzip'
                            else response.body.decode()
                        ),
                    ),
                )
            if response.code is None:
                _clear_line()
                print('\r\033[91mUnable to fetch\033[0m', end='', flush=True)
            else:
                _clear_line()
                print(
                    '\r\033[91mError code {0}\033[0m'.format(
                        response.code.decode(),
                    ),
                    end='',
                    flush=True,
                )
        else:
            _clear_line()
            print(
                '\r\033[91mUnable to connect\033[0m',
                end='',
                flush=True,
            )
        return None

    def _parse() -> Tuple[str, int]:
        """Here we deduce registry host/port based upon input parameters."""
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('route', nargs='?', default=None)
        parser.add_argument('name', nargs='?', default=None)
        parser.add_argument('--wildcard', action='store_true', help='Enable wildcard')
        args, _remaining_args = parser.parse_known_args()
        grout_tld = default_grout_tld
        if args.name is not None and '.' in args.name:
            grout_tld = args.name if args.wildcard else args.name.split('.', maxsplit=1)[1]
        grout_tld_parts = grout_tld.split(':')
        tld_host = grout_tld_parts[0]
        tld_port = 443
        if len(grout_tld_parts) > 1:
            tld_port = int(grout_tld_parts[1])
        return tld_host, tld_port

    tld_host, tld_port = _parse()
    env = None
    attempts = 0
    try:
        while True:
            env = _env(scheme=HTTPS_PROTO, host=tld_host.encode(), port=int(tld_port))
            attempts += 1
            if env is not None:
                print('\rStarting ...' + ' ' * 30 + '\r', end='', flush=True)
                break
            time.sleep(1)
            _clear_line()
            print(
                '\rWaiting for connection {0}'.format('.' * (attempts % 4)),
                end='',
                flush=True,
            )
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(1)

    assert env is not None
    print('\r' + ' ' * 70 + '\r', end='', flush=True)
    Plugins.from_bytes(env['m'].encode(), name='client').grout(env=env['e'])  # type: ignore[attr-defined]


class GroutClientBasePlugin(ABC):
    """Base class for dynamic grout client rules.

    Implementation of this class must be stateless because a new instance is created
    for every route decision making.
    """

    @abstractmethod
    def resolve_route(
        self,
        route: str,
        request: HttpParser,
        origin: HostPort,
        server: HostPort,
    ) -> Tuple[Optional[str], HttpParser]:
        """Returns a valid grout route string.

        You MUST override this method.  This method returns 2-tuple where
        first value is the "route" and second the "request" object.

        For a simple pass through, simply return the "route" argument value itself.
        You can also return a dynamic value based upon "request" and "origin" information.
        E.g. sending to different upstream services based upon request Host header.
        Return None as "route" value to drop the request.

        You can also modify the original request object and return.  Common examples
        include strip-path scenario, where you would like to strip the path before
        sending the request to upstream.
        """
        raise NotImplementedError()
