from typing import Dict
from .types import SelectedVariant

EXPOSURE_EVENT = "$experiment_started"

REQUEST_HEADERS: Dict[str, str] = {
    'X-Scheme': 'https',
    'X-Forwarded-Proto': 'https',
    'Content-Type': 'application/json'
}

def normalized_hash(key: str, salt: str) -> float:
    """Compute a normalized hash using FNV-1a algorithm.
    
    :param key: The key to hash
    :param salt: Salt to add to the hash
    :return: Normalized hash value between 0.0 and 1.0
    """
    hash_value = _fnv1a64(key.encode("utf-8") + salt.encode("utf-8"))
    return (hash_value % 100) / 100.0

def _fnv1a64(data: bytes) -> int:
    """FNV-1a 64-bit hash function.
    
    :param data: Bytes to hash
    :return: 64-bit hash value
    """
    FNV_prime = 0x100000001b3
    hash_value = 0xcbf29ce484222325

    for byte in data:
        hash_value ^= byte
        hash_value *= FNV_prime
        hash_value &= 0xffffffffffffffff  # Keep it 64-bit

    return hash_value

def prepare_common_query_params(token: str, sdk_version: str) -> Dict[str, str]:
    """Prepare common query string parameters for feature flag evaluation.

    :param token: The project token
    :param sdk_version: The SDK version
    :return: Dictionary of common query parameters
    """
    params = {
        'sdk': 'python',
        'sdk_version': sdk_version,
        'token': token
    }

    return params