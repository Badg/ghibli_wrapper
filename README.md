# Ghibli wrapper

A simple wrapper around the Studio Ghibli public api.

[![CI](https://github.com/Badg/ghibli_wrapper/workflows/CI/badge.svg)](https://github.com/Badg/ghibli_wrapper/actions)

Mostly written for the obvious reasons 😊, but I also wanted to learn a bit. In particular, since I'm slowly chipping away on my own web framework smiliar to fastAPI (link: [annoliate](https://github.com/Taev-dev/annoliate)), I was interested in:

+   using fastAPI for the first time!
+   getting more familiar with pydantic, which I'm actually using behind the hood in annoliate anyways. In particular, it was a good excuse to write my first custom type
+   getting VCR.py to work with python-asks

### Some lessons learned

+   Pydantic's API has some rough edges around custom types
+   I don't want to use VCR.py with python-asks
+   freezegun documentation comes from the most recent github commit, which is ahead of freezegun's current pypi version. Guess when freezegun added support for time.monotonic?

### Some caveats

+   The test code is really sloppy, especially for the cache. I was low on time, and it was more important to me to have better test coverage than to have all the tests be well-written (that being said, I didn't actually implement a coverage measurement, so it's all just my approximation)
+   The cache API and, frankly, internal logic could probably use some work, but cacheing is really tricky to get right, application-specific, and time-consuming

## Installation, usage, tests

### With ``poetry``

```bash
# ----- Installation ------
git clone <repo>
poetry install
# ----- Usage ------
poetry run python -m ghibli_wrapper
# ----- Running tests ------
poetry run python -m pytest --import-mode=importlib
```

### With ``pip``

```bash
# ----- Installation ------
git clone <repo>
# In your favorite venv
pip install .
# ----- Usage ------
python -m ghibli_wrapper
# ----- Running tests ------
python -m pytest --import-mode=importlib
```

**Note: this requires a relatively new ``pip`` version** (I believe ``19.0.0`` or above, but don't quote me on that; I tested with 19.2.3).

## Style guide notes

Formatted per pep8 but not pep257. Specifics are in ``.flake8``, but the potentially contentious decisions ones are:

+   Max line length 79 characters
+   Break lines after binary operators, not before ([opinions on this are changing](https://stackoverflow.com/questions/7942586/correct-style-for-line-breaks-when-chaining-methods-in-python/7942617#7942617))
+   Import statements are alphabetized and grouped:
    1.  ``import <stdlib>``
    2.  ``from <stdlib> import <x>``
    3.  (empty line)
    4.  ``import <thirdparty_dep>``
    5.  ``from <thirdparty_dep> import <y>``
    6.  (empty line)
    7.  ``import <internal_dep>``
    8.  ``from <internal_dep> import <z>``
+   Import statements always use full absolute names, eg ``from ghibli_wrapper.utils import <x>``, not ``from .utils import <x>``
+   Docstrings:
    *   Triple single quotes, not triple double (I recognize this is in direct opposition to pep257)
        -   I do this purely for ergonomic reasons
        -   It just occurred to me that in all my years I never really learned to use the left shift, so maybe I'll start changing that
        -   Pre-commit hooks are great for normalizing docstrings anyways
    *   No line break on first line of docstr (``'''Foo...``, not ``'''\nFoo``)
    *   Closing triple quotes on dedicated line
    *   No blank line before closing triple quotes
