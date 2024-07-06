# -*- coding: utf-8 -*-
"""
    proxy.py
    ~~~~~~~~
    ⚡⚡⚡ Fast, Lightweight, Pluggable, TLS interception capable proxy server focused on
    Network monitoring, controls & Application development, testing, debugging.

    :copyright: (c) 2013-present by Abhinav Singh and contributors.
    :license: BSD, see LICENSE for more details.
"""
from typing import Type

from proxy.plugin import (
    ShortLinkPlugin, CacheResponsesPlugin, ManInTheMiddlePlugin,
    ModifyPostDataPlugin, ProposedRestApiPlugin, FilterByURLRegexPlugin,
    FilterByUpstreamHostPlugin, RedirectToCustomServerPlugin,
)
from proxy.http.proxy import HttpProxyBasePlugin
from proxy.http.proxy.auth import AuthPlugin


def get_plugin_by_test_name(test_name: str) -> Type[HttpProxyBasePlugin]:
    plugin: Type[HttpProxyBasePlugin] = ModifyPostDataPlugin
    if test_name == 'test_modify_post_data_plugin':
        plugin = ModifyPostDataPlugin
    elif test_name == 'test_proposed_rest_api_plugin':
        plugin = ProposedRestApiPlugin
    elif test_name == 'test_redirect_to_custom_server_plugin':
        plugin = RedirectToCustomServerPlugin
    elif test_name == 'test_filter_by_upstream_host_plugin':
        plugin = FilterByUpstreamHostPlugin
    elif test_name == 'test_cache_responses_plugin':
        plugin = CacheResponsesPlugin
    elif test_name == 'test_man_in_the_middle_plugin':
        plugin = ManInTheMiddlePlugin
    elif test_name == 'test_filter_by_url_regex_plugin':
        plugin = FilterByURLRegexPlugin
    elif test_name == 'test_shortlink_plugin':
        plugin = ShortLinkPlugin
    elif test_name == 'test_auth_plugin':
        plugin = AuthPlugin
    return plugin
