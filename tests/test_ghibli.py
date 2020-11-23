'''Tests our low-level python wrappers for the Ghibli API.

TODO: this needs tests of the error cases!
'''

import pytest

from ghibli_wrapper.ghibli import get_all_people
from ghibli_wrapper.ghibli import get_all_films
from ghibli_wrapper.ghibli import _GhibliFilmRecord
from ghibli_wrapper.ghibli import _GhibliPersonRecord


# EDITORIAL NOTE: using VCR here means that we're not making live requests
# during tests, but rather loading saved replays from /tests/cassettes
class TestGhibliWithVcrRequestPlayback:

    @pytest.mark.vcr()
    async def test_get_all_people_happy_case(self):
        async for record in get_all_people():
            assert isinstance(record, _GhibliPersonRecord)

    @pytest.mark.vcr()
    async def test_get_all_films_happy_case(self):
        async for record in get_all_films():
            assert isinstance(record, _GhibliFilmRecord)
