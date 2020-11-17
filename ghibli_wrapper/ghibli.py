'''This module contains pythonic wrappers for the studio ghibli API.
These coroutines implement no caching, they simply perform requests.
Only call them when you know you need to hit their servers.
'''
import functools
import json

import asks
import trio

from ghibli_wrapper.exceptions import GhibliApiFailure


GHIBLI_BASE_URL = 'https://ghibliapi.herokuapp.com'
GHIBLI_TIMEOUT_SECONDS = 1
GHIBLI_RETRIES = 2


def _ghibli_request(endpoint, **params):
    '''Decorator to construct quick-and-easy requestors from the ghibli
    API. This isn't super flexible; in particular, we can't do dynamic
    parameters, though you could easily adapt it to support them.
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

            This would also probably be where I would implement circuit
            breaker logic for it, if I had time.
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
                adapted_result = await request_adapter_coro(payload)
            except (Exception, trio.MultiError) as exc:
                raise GhibliApiFailure(endpoint) from exc

            return adapted_result

        return wrapper

    return decorator


@_ghibli_request('/people', fields=['id', 'name', 'films', 'url'])
async def get_all_people(json_response):
    raise NotImplementedError()
    return json_response


@_ghibli_request(
    '/films', fields=['id', 'title', 'release_date', 'description'])
async def get_all_films(json_response):
    raise NotImplementedError()
    return json_response
