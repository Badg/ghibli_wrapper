'''Contains all exceptions used internally to ghibli_wrapper in a single
location with no internal dependencies. This makes it a lot easier to
avoid accidental circular imports in exception handling logic.
'''


class GhilbliWrapperException(Exception):
    '''The base class for all of our internal exceptions. You can catch
    this to handle all expected errors from within ghibli_wrapper;
    anything that would leak through that catch would be a
    ghibli_wrapper bug. This idiom is more useful for libraries than
    applications, so it's probably overkill here, but it takes two
    seconds to code and it protects us against future use as a library.
    '''


class GhibliApiFailure(GhilbliWrapperException):
    '''A catchall error raised when we fail to talk to Studio Ghibli's
    API. This could be them having downtime, network problems between
    us, our wrapper code breaking, or any number of similar issues.
    '''
