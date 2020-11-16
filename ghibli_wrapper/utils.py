from uuid import UUID

import base58


_BASE58_ALPHABET = base58.BITCOIN_ALPHABET.decode()


class HyperlinkFriendlyUuid(UUID):
    '''Okay, I'm going to go on a long and probably unnecessary tangent
    about encoding UUIDs into a format suitable for hyperlinking. But
    first I want to say explicitly: this is the kind of thing you either
    do **everywhere** in an organization, or nowhere. No matter how good
    your devops setup (eg, pinned deps via some lockfile, including hash
    fingerprints), it makes zero sense to add a third-party dep just to
    serialize UUIDs for a single endpoint.

    With that being said, URLs are part of your UX, and they get
    copy/pasted into all sorts of places: twitter, SMS, email, slack,
    you name it. Sometimes grandparents even read them out loud over the
    phone. URLs are the lifeblood of the internet, and I don't think we
    always give them enough thought! So when it comes to encoding binary
    data into a hyperlink, for personal projects, I tend to use
    base58 -- which is pretty rare, except some parts of the
    cryptocurrency world, where it's absolutely ubiquitous. Here's why:

    ```python
    >>> from uuid import UUID
    >>> import base64
    >>> import base58
    >>> test_uuid = UUID('d7fc04d0-37f7-43eb-8d04-d904c3f6bfa5')
    ```

    Okay, let's start out encoding that as hex. Stripping the dashes and
    just using the raw hex is 32 characters. That's pretty big in a URL,
    and though admittedly I've seen much worse, it's not ideal.

    Now you *could* just truncate the hex, but then you ultimately need
    to somehow get the full UUID, which means your backend has to do
    extra work for every single request that uses a UUID, which would
    typically mean either an extra database call or a more complicated
    (and more expensive) query. Plus, you have to be a lot more careful
    about birthday collisions.

    ```python
    >>> f'https://example.com/movies/{test_uuid.hex}'
    'https://example.com/movies/fe93adf22f3a4ec49f685422f1b87c01'
    ```

    Base 64 is more compact -- 24 characters with padding, 22
    without -- but... just look at it. This is really aesthetically
    displeasing. Plus, who knows whose sloppy regex is going to break
    because of the equals signs. Stripping the padding is a bit better,
    but in the python world that means manually removing it on every
    ``encode`` and adding it on every ``decode``.

    ```python
    >>> uuid_b64 = base64.urlsafe_b64encode(test_uuid.bytes).decode()
    >>> f'https://example.com/movies/{uuid_b64}'
    'https://example.com/movies/1_wE0Df3Q-uNBNkEw_a_pQ=='
    ```

    Base58, on the other hand, is almost-and-sometimes-exactly the same
    length as base64, even after stripping padding -- in this case, 22
    characters. It looks much better, has no special characters, avoids
    confusibles like I/l/1, needs no manual modification, and is just
    generally... nicer.

    ```python
    >>> uuid_b58 = base58.b58encode(test_uuid.bytes).decode()
    >>> f'https://example.com/movies/{uuid_b58}
    'https://example.com/movies/TfuAp2ejWADd8CPuNiZ2DS'
    ```

    :tada:
    '''

    @classmethod
    def __get_validators__(cls):
        # Note: if we wanted, we could refactor this to first ensure a string,
        # and *then* convert it to a UUID, but unless the current cls.validate
        # gets too complicated, then that's probably premature generalization
        yield cls.validate

    @classmethod
    def validate(cls, value):
        '''Convert an incoming string value into an instance of our
        custom UUID subclass.
        '''
        # We could technically accept bytes-like here, but we want to be
        # consistent with our serialization
        if not isinstance(value, str):
            raise TypeError('Value must be str')

        try:
            uuid_bytes = base58.b58decode(value)
        except ValueError as exc:
            raise ValueError('Invalid base58') from exc

        try:
            return cls(bytes=uuid_bytes)
        except ValueError as exc:
            # This is a much more descriptive error message than UUID gives us
            raise ValueError('Invalid UUID') from exc

    @classmethod
    def __modify_schema__(cls, field_schema):
        '''Alter the API spec's understanding of this field to reflect
        the validator not being 'just a string' or 'just a UUID'
        '''
        field_schema.update(
            type='string',
            pattern=f'^{_BASE58_ALPHABET}{{22}}$',
            examples=[
                'ELKsbTrMCD9F9yskvTvMMG',
                '4jPP7fngT4arvf3QuCKeDk',
                '9R4rKNKzmBSV27XvkWwjpa'
            ]
        )

    def __str__(self):
        '''Override the default UUID string method, which returns a
        value in hex format with dashes.
        '''
        return base58.b58encode(self.bytes).decode()
