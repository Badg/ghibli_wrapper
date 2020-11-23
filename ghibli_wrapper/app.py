import dataclasses
from typing import List

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ghibli_wrapper.cache import request_through_cache
from ghibli_wrapper.ghibli import get_all_films
from ghibli_wrapper.ghibli import get_all_people
from ghibli_wrapper.ghibli import MOVIE_PEOPLE_LOOKUP
from ghibli_wrapper.utils import HyperlinkFriendlyUUID

app = FastAPI()
app.mount('/static', StaticFiles(directory='static'), name='static')
templates = Jinja2Templates(directory="templates")


@app.get('/api/health', response_class=HTMLResponse)
async def root():
    return 'Hello world!'


@app.get('/movies', response_class=HTMLResponse)
async def get_movies(request: Request):
    '''Get a list of all movies from Ghibli, augmented by fixing the
    list of people appearing in each movie.

    Note that we would typically expect pagination of some sort for
    something with a larger response.
    '''
    people = await request_through_cache(get_all_people)
    movies = await request_through_cache(get_all_films)

    # Since we already have a cache callback system, it would be smart to also
    # cache the results of this operation, since it's expensive too!
    display_movies = []
    for movie_api_record in movies.values():
        people_api_records = [
            people[person_uuid]
            for person_uuid in MOVIE_PEOPLE_LOOKUP[movie_api_record.id]
        ]

        display_movies.append(DisplayFilm(
            id=HyperlinkFriendlyUUID(str(movie_api_record.id)),
            title=movie_api_record.title,
            description=movie_api_record.description,
            release_year=movie_api_record.release_date,
            people=[
                DisplayPerson(
                    id=HyperlinkFriendlyUUID(str(person.id)), name=person.name,
                    url=person.url)
                for person in people_api_records
            ]
        ))

    return templates.TemplateResponse(
        'movies.html',
        {'request': request, 'movies': display_movies})


@app.get('/api/movies')
async def api_get_movies():
    # Note that this shares a cache with the above! That's why I like to keep
    # the caching as close to the upstream request as possible
    movies = await request_through_cache(get_all_films)
    # TODO: cast this into a proper API format. Also note that currently we're
    # leaking some pydantic magic variables into our API
    return list(movies.values())


@app.get('/api/people')
async def api_get_people():
    # Note that this shares a cache with the above! That's why I like to keep
    # the caching as close to the upstream request as possible
    people = await request_through_cache(get_all_people)
    # TODO: cast this into a proper API format. Also note that currently we're
    # leaking some pydantic magic variables into our API
    return list(people.values())


@dataclasses.dataclass
class DisplayPerson:
    id: HyperlinkFriendlyUUID
    name: str
    url: str


@dataclasses.dataclass
class DisplayFilm:
    id: HyperlinkFriendlyUUID
    title: str
    description: str
    release_year: int
    people: List[DisplayPerson]
