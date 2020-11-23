'''Some basic tests for our cache implementation. Could use more
thorough testing, of error cases in particular. This could also probably
use some better test organization, and more specificity of tests (ie,
test only one thing at a time). But these things take time and thought,
and I'm short on both at the moment.
'''
import dataclasses
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from ghibli_wrapper.cache import cacheable
from ghibli_wrapper.cache import get_cache
from ghibli_wrapper.cache import request_through_cache
from ghibli_wrapper.cache import UpsertOnlyCache
from ghibli_wrapper.exceptions import PartnerUnavailable


@dataclasses.dataclass
class MockCacheResult:
    key: Any
    value: Any


class TestCacheability:

    async def test_cacheable(self):
        '''Make sure request_through_cache works with the cacheable
        decorator.
        '''
        @cacheable(UpsertOnlyCache, default_ttl=1, cache_key='key')
        async def noop():
            yield MockCacheResult(key=True, value=True)

        # No need for assert, we just don't want it to raise
        await request_through_cache(noop)

    async def test_uncacheable(self):
        '''Make sure request_through_cache works with the cacheable
        decorator.
        '''
        async def noop():
            yield MockCacheResult(key=True, value=True)

        with pytest.raises(TypeError):
            await request_through_cache(noop)


# This should absolutely be broken down into separate and more specific tests,
# but for time reasons, I'm doing both at once. These could also use a refactor
# to make them a bit less boilerplatey.
# Really just in general, these tests are hard to read. There's too much
# boilerplate and the logic in the test progression isn't super clear
# Note that we've applied the freezegun to all tests force reliable timing
@pytest.mark.freeze_time
class TestUpsertOnlyCacheAndRequestThroughCache:

    async def test_first_request_upstream_successful(self, freezer):
        sentinel = MagicMock()
        cache_key = 'foo'
        cache_value = 0
        cache_ttl = 1

        @cacheable(UpsertOnlyCache, default_ttl=cache_ttl, cache_key='key')
        async def cacheable_mock():
            sentinel()
            yield MockCacheResult(key=cache_key, value=cache_value)

        await request_through_cache(cacheable_mock)
        sentinel.assert_called()

        cache = get_cache(cacheable_mock)
        assert cache.can_fallback_to_stale

    async def test_first_request_upstream_failure(self, freezer):
        sentinel = MagicMock()
        cache_ttl = 1

        @cacheable(UpsertOnlyCache, default_ttl=cache_ttl, cache_key='key')
        async def cacheable_mock_always_fails():
            sentinel()
            # The yield after raise makes sure this is an async generator
            raise PartnerUnavailable()
            yield

        with pytest.raises(PartnerUnavailable):
            await request_through_cache(cacheable_mock_always_fails)

        sentinel.assert_called()

    async def test_cache_hit(self, freezer):
        sentinel = MagicMock()
        cache_key = 'foo'
        cache_value = 0
        cache_ttl = 1

        @cacheable(UpsertOnlyCache, default_ttl=cache_ttl, cache_key='key')
        async def cacheable_mock():
            sentinel()
            yield MockCacheResult(key=cache_key, value=cache_value)

        cache_result, = (await request_through_cache(cacheable_mock)).values()
        assert cache_result.value == cache_value
        sentinel.assert_called()
        sentinel.reset_mock()

        cache_result, = (await request_through_cache(cacheable_mock)).values()
        assert cache_result.value == cache_value
        sentinel.assert_not_called()

    async def test_cache_stale_upstream_successful(self, freezer):
        sentinel = MagicMock()
        cache_key = 'foo'
        cache_value = 0
        cache_ttl = 1

        @cacheable(UpsertOnlyCache, default_ttl=cache_ttl, cache_key='key')
        async def cacheable_mock():
            sentinel()
            yield MockCacheResult(key=cache_key, value=cache_value)

        cache_result, = (await request_through_cache(cacheable_mock)).values()
        assert cache_result.value == cache_value
        sentinel.assert_called()
        sentinel.reset_mock()

        freezer.tick(cache_ttl * 1.5)
        assert get_cache(cacheable_mock).needs_update()

        cache_result, = (await request_through_cache(cacheable_mock)).values()
        assert cache_result.value == cache_value
        sentinel.assert_called()

    async def test_cache_stale_upstream_failure_with_besteffort(
        self, freezer, caplog
    ):
        sentinel = MagicMock()
        cache_key = 'foo'
        cache_value = 0
        cache_ttl = 1

        @cacheable(UpsertOnlyCache, default_ttl=cache_ttl, cache_key='key')
        async def cacheable_mock_always_fails():
            sentinel()
            # The yield after raise makes sure this is an async generator
            raise PartnerUnavailable()
            yield

        cache = get_cache(cacheable_mock_always_fails)
        cache.update(
            {cache_key: MockCacheResult(key=cache_key, value=cache_value)})
        freezer.tick(cache_ttl * 1.5)
        assert cache.needs_update()

        # TODO: we want to swallow the logging here somehow, I just can't find
        # a way to do this for a single test (this is another argument in favor
        # of converting this to an "info" loglevel instead of a warning)
        cache_result, = (await request_through_cache(
            cacheable_mock_always_fails)).values()
        assert cache_result.value == cache_value
        sentinel.assert_called()

        warning_issued = False
        for record in caplog.records:
            if (
                record.name == 'ghibli_wrapper.cache' and
                record.levelname == 'WARNING'
            ):
                warning_issued = True
        assert warning_issued

    async def test_cache_ttl_override(self, freezer):
        sentinel = MagicMock()
        cache_key = 'foo'
        cache_value = 0
        cache_ttl = 1

        @cacheable(UpsertOnlyCache, default_ttl=cache_ttl, cache_key='key')
        async def cacheable_mock():
            sentinel()
            yield MockCacheResult(key=cache_key, value=cache_value)

        cache_result, = (await request_through_cache(cacheable_mock)).values()
        assert cache_result.value == cache_value
        sentinel.assert_called()
        sentinel.reset_mock()

        cache = get_cache(cacheable_mock)
        freezer.tick(cache_ttl * 1.5)
        assert cache.needs_update()
        assert not cache.needs_update(ttl=cache_ttl * 2)

        cache_result, = (await request_through_cache(
            cacheable_mock, ttl=cache_ttl * 2)).values()
        assert cache_result.value == cache_value
        sentinel.assert_not_called()
        sentinel.reset_mock()

        freezer.tick(cache_ttl * 1.5)
        assert cache.needs_update()
        assert cache.needs_update(ttl=cache_ttl * 2)

        cache_result, = (await request_through_cache(
            cacheable_mock, ttl=cache_ttl * 2)).values()
        assert cache_result.value == cache_value
        sentinel.assert_called()

    async def test_cache_update_callback(self, freezer):
        sentinel = MagicMock()
        cache_key = 'foo'
        cache_value = 0
        cache_ttl = 1
        callback_mock = MagicMock()

        @cacheable(
            UpsertOnlyCache, default_ttl=cache_ttl, cache_key='key',
            callbacks=[callback_mock])
        async def cacheable_mock():
            sentinel()
            yield MockCacheResult(key=cache_key, value=cache_value)

        cache_result, = (await request_through_cache(cacheable_mock)).values()
        assert cache_result.value == cache_value
        sentinel.assert_called()
        callback_mock.assert_called()
        sentinel.reset_mock()
        callback_mock.reset_mock()

        cache_result, = (await request_through_cache(cacheable_mock)).values()
        assert cache_result.value == cache_value
        sentinel.assert_not_called()
        callback_mock.assert_not_called()
