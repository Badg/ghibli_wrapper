'''Contains caching logic for requests.

This module assumes a few things code-wise:
+   all cacheable request coroutines are in fact async iterators
+   each result from the async iterator is a separate cache item. its
    cache key is determined by the cache_key parameter in @cacheable

Side note: yes, we could have gone with an API that added a @cache
decorator to the request coroutine, and done the caching transparently.
However, that makes it really difficult to test the low-level requests,
since you would need to "peel" the decorator (doable but very annoying)
away for those tests. That also would make forcible cache updates much
more awkward to implement, if we wanted them, and just generally makes
things more complicated. Put simply: explicit cache use is better than
implicit!

With different semantics that could even be really simple code, for
example, if we used cachetools' TTLCache. However, we want different
semantics than cachetools (in particular, the ability to serve stale
results when upstream failures happen).

Note that this is also a single-server cache. Depending on application,
it might be more appropriate to implement a distributed cache,
possible/probably with redis.

Caching in general can be very finicky and very application-specific.
This was written to be a somewhat middle-ground cache of (what amounts
to) a proxy of a third-party service, with support for some limited
enrichment of the proxied third-party API. In other words, it wasn't
written to be specific to our wrapper of Studio Ghibli's API, but it
*was* written specifically for that kind of application.

Additionally, we're taking advantage of the fact the Studio Ghibli
doesn't have *that* many films, nor *that* many people, and we therefore
don't need to worry about memory constraints and/or pagination.

We're also assuming that our expected traffic is relatively light and/or
sporadic. If we were expecting consistently high traffic, it would
probably make sense to prefetch the cache to minimize long-tail latency
on requests. You could implement that fairly easily with a background
task that made a ``request_through_cache`` request repeatedly, on an
interval slightly less than the cache's TTL. Or, you could implement a
stale-while-revalidate pattern (ie, the TTL starts the cache refreshsing
process, but we continue serving stale results until the cache refresh
completes), though that has the obvious product consequence that you'll
sometimes be serving results that are slightly more stale than you might
otherwise expect.
'''

import functools
import logging
import time
import types

from ghibli_wrapper.exceptions import PartnerUnavailable

logger = logging.getLogger(__name__)
_CACHE_TYPE_ATTR = '__request_cache__'
_CACHE_KEYGEN_ATTR = '__request_cache_key__'


def cacheable(cache_type, *, default_ttl, cache_key, callbacks=None):
    '''Decorator for marking a coroutine as cacheable. Adds an instance
    of the desired cache_type to the coroutine, with a default ttl as
    specified (in seconds). cache_key specifies how to store the result,
    either as a callable with one argument (the item to cache), or a
    string naming the attribute to use.

    **Note that the coroutine must be an async iterator!!**

    Use like this:

        @cacheable(UpsertOnlyCache, default_ttl=60, cache_key='id')
        async def request_something():
            ...
    '''
    if isinstance(cache_key, str):
        # Unfortunately we can't use a partial for the second positional-only
        # arg
        @functools.wraps(getattr)
        def cache_keygenner(obj):
            return getattr(obj, cache_key)

    elif callable(cache_key):
        cache_keygenner = cache_key

    else:
        raise TypeError('cache_key must be string or callable')

    def decorator(coro):
        '''The inner (actual) decorator for the coroutine as described
        above.
        '''
        setattr(
            coro, _CACHE_TYPE_ATTR,
            cache_type(default_ttl=default_ttl, callbacks=callbacks))
        setattr(coro, _CACHE_KEYGEN_ATTR, cache_keygenner)
        return coro

    return decorator


class UpsertOnlyCache:
    '''A dependable appendable cache. It assumes that cached objects are
    never removed, though they may be updated. So you can update keys,
    and can insert new keys, but cannot remove keys.

    Note that if we *did* support removal of items, we would want to
    delay purging them until the next successful request, in order to
    support falling back to stale results.
    '''

    def __init__(self, *args, default_ttl, callbacks=None, **kwargs):
        # TODO: we need more docs for this; particularly re: callbacks
        super().__init__(*args, **kwargs)
        self.default_ttl = default_ttl
        self._last_update = None
        # We *could* subclass dict, but we really don't want to, because we
        # want all mutation methods to also change self._last_update. Better
        # to leave some un-implemented than inherit from dict and accidentally
        # mutate without updating the timestamp because we forgot to implement
        # that specific logic. In other words, it's more important to us to
        # behave like a cache than like a dict
        self._cache = {}
        self._cache_view = types.MappingProxyType(self._cache)

        # Update callbacks are an awkward thing. I don't *really* want to use
        # them. However, we want all of:
        #   1. best-effort behavior like "fall back to stale results"
        #   2. serving both "films" and "people" as individual endpoints
        #   3. performing a data transform to look up films -> {people}
        # Callbacks seem like the least-bad way of supporting all of those at
        # the same time.
        if callbacks is None:
            self._callbacks = []
        else:
            self._callbacks = callbacks

    def needs_update(self, ttl=None):
        '''Checks to see if we need to update the cache. Returns bool.
        Pass an optional ttl to override the default.
        '''
        if self._last_update is None:
            return True

        elif ttl is None:
            use_ttl = self.default_ttl

        else:
            use_ttl = ttl

        # Sure, we *could* use datetime, but why? Everything that we're doing
        # is in terms of seconds and on a single server. This is simpler and
        # more direct!
        return time.monotonic() - self._last_update >= use_ttl

    def update(self, other):
        '''Update the cache using other.'''
        # We're doing this in this order so that if there's an error in the
        # update, we don't change self._last_update
        self._cache.update(other)
        self._last_update = time.monotonic()

        for callback in self._callbacks:
            callback(self)

    def get(self, *args, **kwargs):
        '''Identical semantics to dict.get()'''
        return self._cache.get(*args, **kwargs)

    @property
    def can_fallback_to_stale(self):
        '''Returns boolean indicating whether or not we have stale
        results we could fall back on.
        '''
        return self._last_update is not None

    @property
    def all(self):
        '''Return a read-only view of the whole cache.'''
        # This could probably stand to have some explicit handling of the edge
        # case where we haven't yet completed an upstream request (and the
        # cache is therefor unpopulated)
        return self._cache_view


def get_cache(cacheable_coro):
    cache = getattr(cacheable_coro, _CACHE_TYPE_ATTR, None)
    if cache is None:
        raise TypeError(
            'Must decorate with @cacheable to get_cache!')
    return cache


async def request_through_cache(cacheable_coro, best_effort=True, ttl=None):
    '''Gets the results of cacheable_coro, which must be an async
    iterator decorated with @cacheable. If the cacheable_coro has been
    requested within the cache's default_ttl (or within an explicit
    ttl provided to this coro), serves completely from the cache.
    Otherwise, performs an upstream request and updates the cache.

    If best_effort, then upstream errors are logged and swallowed, and
    results are served from the cache regardless of staleness. If not
    best_effort, stale cache results are never returned.

    Depending on the application, this might also be a good place to
    implement circuit breaker logic, but I'm cutting this for time
    reasons. In our particular Ghibli application, I think I would
    probably put that in a separate circuitbreakers.py module, and
    implement them there.
    '''
    cache = getattr(cacheable_coro, _CACHE_TYPE_ATTR, None)
    keygenner = getattr(cacheable_coro, _CACHE_KEYGEN_ATTR, None)
    if cache is None or keygenner is None:
        raise TypeError(
            'Must decorate with @cacheable to request_through_cache!')

    if cache.needs_update(ttl):
        try:
            # Note that this only works for small results. Large responses
            # could run into memory issues
            cache.update(
                {keygenner(item): item async for item in cacheable_coro()}
            )

        except PartnerUnavailable as exc:
            if best_effort and cache.can_fallback_to_stale:
                logger.warning(
                    'Partner unavailable for %s! Using stale cache.',
                    cacheable_coro,
                    exc_info=exc)
                return cache.all

            # Either we explicitly said best_effort=False (and therefore, we
            # never want stale results), or we've never made a successful
            # cached upstream request. Choosing to reraise in the latter case
            # is ultimately a product decision, and opinions may differ on
            # whether that's the best approach
            else:
                raise

        else:
            return cache.all

    else:
        return cache.all
