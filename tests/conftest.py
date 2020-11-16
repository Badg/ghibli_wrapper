import functools

import pydantic.typing
import pytest


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
