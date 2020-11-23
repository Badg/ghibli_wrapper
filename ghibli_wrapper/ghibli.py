'''This module contains pythonic wrappers for the studio ghibli API.
These coroutines implement no caching, they simply perform requests.
Only call them when you know you need to hit their servers.
'''
import collections
import dataclasses
import functools
import json
import logging
from typing import List
from uuid import UUID

import asks
import pydantic
import trio

from ghibli_wrapper.cache import cacheable
from ghibli_wrapper.cache import UpsertOnlyCache
from ghibli_wrapper.exceptions import GhibliApiFailure


GHIBLI_BASE_URL = 'https://ghibliapi.herokuapp.com'
GHIBLI_TIMEOUT_SECONDS = 1
GHIBLI_RETRIES = 2

logger = logging.getLogger(__name__)

# I would prefer not to store this at the module level, but since FastAPI
# uses module-level *everything* anyways, and it's suuuuper convenient...
# Note that we're assuming that people are never removed from movies, and that
# movies are never un-released
MOVIE_PEOPLE_LOOKUP = collections.defaultdict(set)
_GHIBLI_TTL = 60


def _update_moviepeople_lookup(people_cache):
    # This is a very expensive operation -- O(n^2). It wouldn't scale well to
    # large numbers of films and/or lots of people. The upside is that because
    # we're caching it, we don't have to do it on every request!
    for person_id, person in people_cache.all.items():
        for film_url_info in person.films:
            MOVIE_PEOPLE_LOOKUP[film_url_info.uuid].add(person.id)


# Decorators don't play well with the mccabe complexity checker :(
def _ghibli_request(endpoint, **params):  # noqa: C901
    '''Decorator to construct quick-and-easy requestors from the ghibli
    API. This isn't super flexible; in particular, we can't do dynamic
    parameters, though you could easily adapt it to support them.

    I'm not 100% happy with decorators that alter the signature of the
    function/coroutine they decorate, but they can also be very
    expedient.
    '''
    # This happens at decoration-time, so there's no performance penalty. We
    # don't want developers spelling out the whole URL in each of the endpoints
    # in case the base URL changes!
    if endpoint.startswith(GHIBLI_BASE_URL):
        raise ValueError('Endpoints should exclude the base URL for ghibli!')

    endpoint = f'{GHIBLI_BASE_URL}{endpoint}'

    # Normalize lists into comma-separated strings
    for key, value in params.items():
        if not isinstance(value, str):
            try:
                iter(value)
            # We want this to fail fast or we get 500's from ghibli because
            # asks is too forgiving. *ask* me how I know!
            except TypeError as exc:
                raise TypeError(
                    'Cannot convert to query string!', key, value) from exc
            else:
                params[key] = ','.join(value)

    def decorator(request_adapter_coro):
        # Note: we're memoizing the decorator parameters purely for performance
        # reasons. That might be overkill, but it's also less than a single
        # line of code to (minutely) speed up every ghibli request we make
        @functools.wraps(request_adapter_coro)
        async def wrapper(*args, _endpoint=endpoint, _params=params, **kwargs):
            '''Adds a lot of error handling to the ghibli API.
            '''
            try:
                response = await asks.get(
                    _endpoint,
                    params=params,
                    timeout=GHIBLI_TIMEOUT_SECONDS,
                    retries=GHIBLI_RETRIES,
                    headers={'Accept': 'application/json'}
                )
            except asks.AsksException as exc:
                raise GhibliApiFailure(endpoint) from exc

            if response.status_code != 200:
                raise GhibliApiFailure(
                    endpoint, response.status_code, response.body)

            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise GhibliApiFailure(endpoint) from exc

            try:
                # This is awkward. In particular, it forces out request adapter
                # to always be an async iterable. However, wrapping an async
                # generator is super complicated (I mean there's a whole note
                # in pep525 explaining why "yield from" wasn't included), so
                # the route of least resistance is to just enforce consistent
                # semantics from all wrapped requestors.
                async for adapted_result in request_adapter_coro(payload):
                    yield adapted_result

            except (Exception, trio.MultiError) as exc:
                raise GhibliApiFailure(endpoint) from exc

        return wrapper

    return decorator


@cacheable(UpsertOnlyCache, default_ttl=_GHIBLI_TTL, cache_key='id',
           callbacks=[_update_moviepeople_lookup])
@_ghibli_request('/people', fields=['id', 'name', 'films', 'url'])
async def get_all_people(json_response):
    '''Get all the people in all Studio Ghibli films from their API.
    Returns an async iterator; each object has their ID (as per ghibli),
    name, URL, and a list of the films they appeared in.
    '''
    # Note that in a larger API we would expect to need to handle pagination.
    # Async iterators make this easy to handle, though we would need to alter
    # our _ghibli_request decorator to accommodate
    async for res in _GhibliPersonRecord.iterate_into_instances(json_response):
        yield res


@cacheable(UpsertOnlyCache, default_ttl=_GHIBLI_TTL, cache_key='id')
@_ghibli_request(
    '/films', fields=['id', 'title', 'release_date', 'description'])
async def get_all_films(json_response):
    '''Get all the films in the Studio Ghibli filmography from their
    API. Returns an async iterator; each object has their ID (as per
    ghibli), title, description, and release year.
    '''
    # Note that in a larger API we would expect to need to handle pagination
    # Async iterators make this easy to handle, though we would need to alter
    # our _ghibli_request decorator to accommodate
    async for res in _GhibliFilmRecord.iterate_into_instances(json_response):
        yield res


class _GhibliRecordMixin:

    @classmethod
    async def iterate_into_instances(cls, iterable_response):
        '''Helper iterator to add error handling to Ghibli responses that
        are just lists of objects.
        '''
        # Note that this is strict -- if Ghibli gives us extra information,
        # it'll fail. That's a bit fragile, so a future improvement might be to
        # update the code to be more forgiving of ghibli responses that
        # erroneously give us more fields than we asked for
        had_any_success = None
        for record in iterable_response:
            try:
                yield cls(**record)
            except (TypeError, pydantic.ValidationError) as exc:
                # Reasonable minds may disagree on this choice of loglevel here
                logger.warning(
                    'Failed to parse ghibli response!', exc_info=exc)
                # | comparison doesn't work between NoneType and Bool; use this
                # equivalent instead
                had_any_success = had_any_success or False
            else:
                had_any_success = True

        # If we had results from ghibli, but we failed to parse ALL of them,
        # then that's likely our fault, and we should raise to trip circuit
        # breakers. We specifically want False here, since we want to ignore
        # the None case where Ghibli returned no results
        if had_any_success is False:
            raise GhibliApiFailure('Had results, but none parsed')


@dataclasses.dataclass(frozen=True)
class _GhibliFilmUrl:
    url: str
    uuid: UUID

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value):
        if not isinstance(value, str):
            raise TypeError('Value must be a string!')

        # This is fragile, but also expedient. Ideally we would be refreshing
        # our VCR (test request playback) captures regularly to make sure the
        # Ghibli API hadn't been updated in a way that changed this.
        # Ultimately, this would be relying on circuit breakers to gracefully
        # failover from unannounced partner changes like that.
        __, __, uuid_hex = value.rpartition('/')
        return cls(url=value, uuid=UUID(uuid_hex))


@pydantic.dataclasses.dataclass(frozen=True)
class _GhibliFilmRecord(_GhibliRecordMixin):
    # We want to preserve the exact result we received here, so don't convert
    # immediately to hyperlinkfriendlyuuid
    id: UUID
    title: str
    description: str
    release_date: int


@pydantic.dataclasses.dataclass(frozen=True)
class _GhibliPersonRecord(_GhibliRecordMixin):
    # We want to preserve the exact result we received here, so don't convert
    # immediately to hyperlinkfriendlyuuid
    id: UUID
    name: str
    # Note that these are a list of URLs, which contain the UUID, but isn't
    # simply the uuid itself.
    films: List[_GhibliFilmUrl]
    url: str
