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
import queue
import threading
import multiprocessing
from multiprocessing import connection

import unittest
from unittest import mock

from proxy.core.event import EventQueue, EventDispatcher, eventNames


class TestEventDispatcher(unittest.TestCase):

    def setUp(self) -> None:
        self.dispatcher_shutdown = threading.Event()
        self.manager = multiprocessing.Manager()
        self.event_queue = EventQueue(self.manager.Queue())
        self.dispatcher = EventDispatcher(
            shutdown=self.dispatcher_shutdown,
            event_queue=self.event_queue,
        )

    def tearDown(self) -> None:
        self.dispatcher_shutdown.set()
        self.manager.shutdown()

    def test_empties_queue(self) -> None:
        self.event_queue.publish(
            request_id='1234',
            event_name=eventNames.WORK_STARTED,
            event_payload={'hello': 'events'},
            publisher_id=self.__class__.__qualname__,
        )
        self.dispatcher.run_once()
        with self.assertRaises(queue.Empty):
            self.dispatcher.run_once()

    @mock.patch('time.time')
    def subscribe(self, mock_time: mock.Mock) -> connection.Connection:
        mock_time.return_value = 1234567
        relay_recv, relay_send = multiprocessing.Pipe()
        self.event_queue.subscribe(sub_id='1234', channel=relay_send)
        # consume the subscribe event
        self.dispatcher.run_once()
        # assert subscribed ack
        self.assertEqual(
            relay_recv.recv(), {
                'event_name': eventNames.SUBSCRIBED,
            },
        )
        # publish event
        self.event_queue.publish(
            request_id='1234',
            event_name=eventNames.WORK_STARTED,
            event_payload={'hello': 'events'},
            publisher_id=self.__class__.__qualname__,
        )
        # consume
        self.dispatcher.run_once()
        # assert recv
        r = relay_recv.recv()
        print(r)
        self.assertEqual(
            r, {
                'request_id': '1234',
                'process_id': os.getpid(),
                'thread_id': threading.get_ident(),
                'event_timestamp': 1234567,
                'event_name': eventNames.WORK_STARTED,
                'event_payload': {'hello': 'events'},
                'publisher_id': self.__class__.__qualname__,
            },
        )
        return relay_recv

    def test_subscribe(self) -> None:
        self.subscribe()

    def test_unsubscribe(self) -> None:
        relay_recv = self.subscribe()
        self.event_queue.unsubscribe('1234')
        self.dispatcher.run_once()
        # assert unsubscribe ack
        self.assertEqual(
            relay_recv.recv(), {
                'event_name': eventNames.UNSUBSCRIBED,
            },
        )
        self.event_queue.publish(
            request_id='1234',
            event_name=eventNames.WORK_STARTED,
            event_payload={'hello': 'events'},
            publisher_id=self.__class__.__qualname__,
        )
        self.dispatcher.run_once()
        with self.assertRaises(EOFError):
            relay_recv.recv()

    # def test_unsubscribe_on_broken_pipe_error(self) -> None:
    #     pass

    # def test_run(self) -> None:
    #     pass
