import functools
import logging
import urllib.parse

import asks
import pydantic.typing
import pytest
import vcr
from vcr.request import Request as VcrRequest


@pytest.fixture(autouse=True)
def fixup_pydantic(monkeypatch):
    '''Pydantic tries to get smart about checking sys.modules for
    resolving type annotations, which... well, it's pretty convoluted
    and it doesn't play nicely with pytest.
    '''
    @functools.wraps(pydantic.typing.resolve_annotations)
    def resolve_annotations_fixup(
        raw_annotations, module_name,
        _early_bound_original_function=pydantic.typing.resolve_annotations
    ):
        '''Just strip any module name that was supplied if it starts
        with 'test_', since it won't exist. This is quick and dirty,
        but it gets the job done as long as we don't do anything
        sophisticated with test discovery logic and keep to a
        test_X naming convention.
        '''
        # I would prefer this to be "if module_name is None", but pydantic's
        # source code uses truthiness, so I'm not sure if it's passing a
        # sentinel or something
        if module_name and module_name.startswith('test_'):
            module_name = None

        # We're using this as a patch, so we can't be late binding, or we'll
        # have infinite recursion -- hence memoizing the original in the
        # function signature
        return _early_bound_original_function(raw_annotations, module_name)

    # This is tricky, because pydantic has already (internally) imported its
    # own copy of resolve_annotations within pydantic.main, so we have to
    # patch it there as well
    monkeypatch.setattr(
        pydantic.typing, 'resolve_annotations', resolve_annotations_fixup)
    monkeypatch.setattr(
        pydantic.main, 'resolve_annotations', resolve_annotations_fixup)


@pytest.fixture(autouse=True)
def run_asks_init():
    asks.init('trio')


async def vcr_record_response(cassette, vcr_request, response):
    '''Stub to record an asks response into a VCR request/response
    chain.

    Heavily based on the VCR stub for aiohttp; see
    https://github.com
        /kevin1024/vcrpy/blob/master/vcr/stubs/aiohttp_stubs.py
    '''
    if isinstance(response, asks.response_objects.StreamResponse):
        raise NotImplementedError('no VCR yet for streaming asks responses')

    vcr_response = dict(
        status={
            'code': response.status_code,
            'message': response.reason_phrase
        },
        headers=response.headers,
        # VCR uses strict typing around bytes() objects when loading, but asks
        # uses a bytesarray for response.body, so VCR raises. This is a quick
        # but effective workaround. We could also use a different serializer.
        body={'string': bytes(response.body)},
        url=response.url
    )

    cassette.append(vcr_request, vcr_response)


async def vcr_record_responses(cassette, vcr_request, response):
    '''Stub for following redirects in an asks request while recording
    into a series of VCR request/response chains.

    Heavily based on the VCR stub for aiohttp; see
    https://github.com
        /kevin1024/vcrpy/blob/master/vcr/stubs/aiohttp_stubs.py
    '''
    if response.history:
        raise NotImplementedError('no vcr yet for redirected responses')

    else:
        await vcr_record_response(cassette, vcr_request, response)


def vcr_play_responses(cassette, vcr_request):
    '''Converts the VCR's version of the request's response into
    something that matches asks' Response API.
    '''
    vcr_response = cassette.play_response(vcr_request)
    # Note that we don't support redirects right now, so we don't have to
    # worry about that
    return asks.response_objects.Response(
        # Punting on these. Dunno how to store it along with the VCR cassette
        # and don't want to take the time to find out; getting VCR running has
        # already taken way too long for what I'm using it for
        encoding='utf-8',
        http_version='1.1',
        status_code=vcr_response['status']['code'],
        reason_phrase=vcr_response['status']['message'],
        headers=vcr_response['headers'],
        body=vcr_response['body'].get('string', b''),
        method=vcr_request.method,
        url=vcr_request.url,
    )


vcr_logger = logging.getLogger('vcr.asks')


def vcr_request(cassette, real_request):
    '''VCR is a synchronous library. We need to bind the cassette into
    a closure wrapping asks.request, so that it can store requests per
    above. Since we'll have patched asks.request at this point, we also
    need the original request method. This outer function creates the
    closure around the actual request coroutine that we need for both
    of those things to happen.
    '''
    @functools.wraps(real_request)
    async def wrapped_request(method, url, **kwargs):
        '''Actually wrap asks.request, storing cassettes as needed.

        Heavily based on the VCR stub for aiohttp; see
        https://github.com
            /kevin1024/vcrpy/blob/master/vcr/stubs/aiohttp_stubs.py
        '''
        # IMPORTANT NOTE! We're ignoring the other headers that asks adds into
        # the request here, so the server response could potentially change if
        # asks modifies its header prep logic in a new version and we
        # subsequently upgrade to that newer asks version. Fixing this is not
        # simple, so I'm punting on it here. We're also ignoring several
        # potentially-important but tricky things like authentication headers,
        # cookies, etc, but ghibli doesn't use any of them, so...
        headers = kwargs.get('headers')
        # Query params
        params = kwargs.get('params')

        # Possible request bodies. Unlike asks-added headers and auth, this
        # is pretty trivial to raise on, and much more likely to be
        # accidentally used down the road
        data = kwargs.get('data')
        json_data = kwargs.get('json')
        if data or json_data:
            raise NotImplementedError()

        url_with_query = f'{url}?{urllib.parse.urlencode(params)}'
        vcr_request = VcrRequest(method, url_with_query, None, headers)

        if cassette.can_play_response_for(vcr_request):
            # Logging has semantics assigned to %s so don't use format strings!
            # We want to preserve the difference between the log message and
            # the interpolated values. VCR source misbehaves here.
            vcr_logger.info(
                'Playing response for %s from cassette', vcr_request)
            response = vcr_play_responses(cassette, vcr_request)
            # Note: this is where we'd need to handle redirects
            return response

        elif cassette.write_protected and cassette.filter_request(vcr_request):
            raise vcr.errors.CannotOverwriteExistingCassetteException(
                cassette=cassette, failed_request=vcr_request)

        else:
            vcr_logger.info(
                '%s not in cassette, performing real request', vcr_request)

            response = await real_request(method, url, **kwargs)
            await vcr_record_responses(cassette, vcr_request, response)
            return response

    return wrapped_request


@pytest.fixture(scope='session', autouse=True)
def fixup_vcr():
    '''The documentation on VCR custom patches was actually *so lacking*
    (and the source code so convoluted) that it was faster for me to
    just bypass their dedicated way of adding custom patches and inject
    my own asks patch into their builtin patch construction mechanism.

    This... kinda turned me off of using VCR in the future, if I'm being
    honest. I love the idea of it, but the implementation makes it
    really tough to use lesser-known request libraries like asks.
    '''

    def build(self):
        for asks_coro_tuple in self._asks():
            yield self._build_patcher(*asks_coro_tuple)
        yield from self._old_build()

    # Memoizing here to bind the original request coro (otherwise it would
    # be recursively patched, just like with pydantic above)
    def asker(self, _real_request=asks.request):
        new_request = vcr_request(self._cassette, _real_request)
        # This isn't at all DRY, but it feels easier to read than a for loop
        yield asks, 'request', new_request
        yield asks, 'get', functools.partial(new_request, "GET")
        yield asks, 'head', functools.partial(new_request, "HEAD")
        yield asks, 'post', functools.partial(new_request, "POST")
        yield asks, 'put', functools.partial(new_request, "PUT")
        yield asks, 'delete', functools.partial(new_request, "DELETE")
        yield asks, 'options', functools.partial(new_request, "OPTIONS")
        yield asks, 'patch', functools.partial(new_request, "PATCH")

    # We're going to in-place patch instead of subclass, so that we don't
    # need to worry about hunting down all of the imports VCR uses
    # We really want this to be global; we're patching VCR to understand
    # another patch, while keeping the rest of the patchers intact. This isn't
    # something we want to ever turn off.
    vcr.patch.CassettePatcherBuilder._old_build = \
        vcr.patch.CassettePatcherBuilder.build
    vcr.patch.CassettePatcherBuilder.build = build
    # Matching VCR's internal naming scheme. Not happy about any of this!
    vcr.patch.CassettePatcherBuilder._asks = asker
