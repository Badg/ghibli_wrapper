'''Well this was meant to be a test file for the whole app, using
httpx and AsyncClient as documented in the FastAPI docs:
https://fastapi.tiangolo.com/advanced/async-tests/

But, I ran out of time, so I did the app testing manually. That is,
beyond this one super, super simple test of the health check endpoint.
'''
import pytest
from httpx import AsyncClient

from ghibli_wrapper.app import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url='http://test') as client:
        response = await client.get('/api/health')
        assert response.status_code == 200
