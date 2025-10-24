import re
import pytest
import random
import string
from .utils import generate_traceparent, normalized_hash

class TestUtils:
    def test_traceparent_format_is_correct(self):
        traceparent = generate_traceparent()

        # W3C traceparent format: 00-{32 hex chars}-{16 hex chars}-{2 hex chars}
        # https://www.w3.org/TR/trace-context/#traceparent-header
        pattern = r'^00-[0-9a-f]{32}-[0-9a-f]{16}-01$'

        assert re.match(pattern, traceparent), f"Traceparent '{traceparent}' does not match W3C format"

    @pytest.mark.parametrize("key,salt,expected_hash", [
        ("abc", "variant", 0.72),
        ("def", "variant", 0.21),
    ])
    def test_normalized_hash_for_known_inputs(self, key, salt, expected_hash):
        result = normalized_hash(key, salt)
        assert result == expected_hash, f"Expected hash of {expected_hash} for '{key}' with salt '{salt}', got {result}"