from uuid import UUID

import pytest
from pydantic import BaseModel
from pydantic import ValidationError

from ghibli_wrapper.utils import HyperlinkFriendlyUUID


class TestHyperlinkFriendlyUUID:
    '''This tests that we correctly implemented our UUID <-> base58
    custom type.
    '''

    @pytest.mark.parametrize(
        'base58_uuid,uuid_hex',
        [
            ('MA9LL8hNJsVWpsqBB1KoP9', 'a33d9a4a-089b-42ac-a054-28d155b6530c'),
            ('RPcRwkc1c8ZWoYcFWWcuMY', 'c583867c-630f-41a0-9e09-e99be95fc75f'),
            ('FDWtLH3E6LbRhpWh736Fij', '731f48a6-7e47-4e6d-9796-5944c1c56994'),
            ('Xe5bBwnWKL7EznMmS7Z9su', 'f81f81f5-0762-4a35-9b94-e0816d36d4a8'),
            ('LUU2nBvvqfr2W36qSMAdMn', '9db35fe4-210e-492d-9651-f233e3e06b8d')
        ]
    )
    def test_happy_case(self, base58_uuid, uuid_hex):
        '''Test that correct base58 UUIDs do, in fact, validate and
        deserialize to our UUID subclass.
        '''
        # Note that we need to define this within the test, since we have to
        # fixture a monkeypatch to pydantic (see conftest.py)
        class _HFUuidModel(BaseModel):
            base58_uuid: HyperlinkFriendlyUUID

            class Config:
                arbitrary_types_allowed = True

        deserialized = _HFUuidModel(base58_uuid=base58_uuid)
        assert deserialized.base58_uuid == UUID(uuid_hex)

    @pytest.mark.parametrize(
        'invalid_input',
        [
            # These are just... wrong
            ('foo',),
            (1,),
            # These are all valid uuids, but in the wrong input format
            ('9db35fe4-210e-492d-9651-f233e3e06b8d',),
            (b'\x9d\xb3_\xe4!\x0eI-\x96Q\xf23\xe3\xe0k\x8d',),
        ]
    )
    def test_failures(self, invalid_input):
        '''Test that incorrect base58 UUIDs raise validation errors.
        '''
        # Note that we need to define this within the test, since we have to
        # fixture a monkeypatch to pydantic (see conftest.py)
        class _HFUuidModel(BaseModel):
            base58_uuid: HyperlinkFriendlyUUID

            class Config:
                arbitrary_types_allowed = True

        with pytest.raises(ValidationError):
            _HFUuidModel(base58_uuid=invalid_input)

    # Parameterizing this is probably overkill, but at least it gives us a
    # consistent place to store test vectors
    @pytest.mark.parametrize(
        'base58_uuid,uuid_hex',
        [
            ('MA9LL8hNJsVWpsqBB1KoP9', 'a33d9a4a-089b-42ac-a054-28d155b6530c'),
            ('RPcRwkc1c8ZWoYcFWWcuMY', 'c583867c-630f-41a0-9e09-e99be95fc75f'),
            ('FDWtLH3E6LbRhpWh736Fij', '731f48a6-7e47-4e6d-9796-5944c1c56994'),
            ('Xe5bBwnWKL7EznMmS7Z9su', 'f81f81f5-0762-4a35-9b94-e0816d36d4a8'),
            ('LUU2nBvvqfr2W36qSMAdMn', '9db35fe4-210e-492d-9651-f233e3e06b8d')
        ]
    )
    def test_stringify(self, base58_uuid, uuid_hex):
        '''Test that our UUID subclass str()'s into a valid base58 UUID.
        '''
        assert str(HyperlinkFriendlyUUID(uuid_hex)) == base58_uuid
