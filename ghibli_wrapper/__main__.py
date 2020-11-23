import asyncio

from hypercorn.config import Config
from hypercorn.asyncio import serve

from ghibli_wrapper.app import app

USE_PORT = 8000


async def main():
    config = Config()
    config.bind = [f'localhost:{USE_PORT}']

    await serve(app, config)


if __name__ == '__main__':
    asyncio.run(main())
