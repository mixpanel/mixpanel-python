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

    def test_normalized_hash_is_between_0_and_1(self):
        for _ in range(100):
            length = random.randint(5, 20)
            random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
            random_salt = ''.join(random.choices(string.ascii_letters, k=10))
            result = normalized_hash(random_string, random_salt)
            assert 0.0 <= result < 1.0, f"Hash value {result} is not in range [0, 1] for input '{random_string}'"
