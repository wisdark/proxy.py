# -*- coding: utf-8 -*-
"""
    proxy.py
    ~~~~~~~~
    ⚡⚡⚡ Fast, Lightweight, Pluggable, TLS interception capable proxy server focused on
    Network monitoring, controls & Application development, testing, debugging.

    :copyright: (c) 2013-present by Abhinav Singh and contributors.
    :license: BSD, see LICENSE for more details.
"""
import time

import unittest

from proxy.common.leakage import Leakage


class TestLeakage(unittest.TestCase):

    def test_initial_consume_no_tokens(self) -> None:
        # Test consuming with no tokens available initially
        rate = 100  # bytes per second
        bucket = Leakage(rate)
        self.assertEqual(
            bucket.consume(150),
            100,
        )  # No tokens yet, so expect 0 bytes to be sent

    def test_consume_with_refill(self) -> None:
        # Test consuming with refill after waiting
        rate = 100  # bytes per second
        bucket = Leakage(rate)
        time.sleep(1)  # Wait for a second to allow refill
        self.assertEqual(bucket.consume(50), 50)  # 50 bytes should be available

    def test_consume_above_leak_rate(self) -> None:
        # Test attempting to consume more than the leak rate after a refill
        rate = 100  # bytes per second
        bucket = Leakage(rate)
        time.sleep(1)  # Wait for a second to allow refill
        self.assertEqual(bucket.consume(150), 100)  # Only 100 bytes should be allowed

    def test_repeated_consume_with_partial_refill(self) -> None:
        # Test repeated consumption with partial refill
        rate = 100  # bytes per second
        bucket = Leakage(rate)

        time.sleep(1)  # Allow tokens to accumulate
        bucket.consume(80)  # Consume 80 bytes, should leave 20
        time.sleep(0.5)  # Wait half a second to refill by 50 bytes

        self.assertEqual(bucket.consume(50), 50)  # 50 bytes should be available now

    def test_negative_token_guard(self) -> None:
        # Ensure tokens do not go negative
        rate = 100  # bytes per second
        bucket = Leakage(rate)
        time.sleep(1)  # Allow tokens to accumulate
        bucket.consume(150)  # Consume all available tokens
        self.assertEqual(bucket.consume(10), 0)  # Should return 0 as no tokens are left
        self.assertEqual(bucket.tokens, 0)  # Tokens should not be negative
