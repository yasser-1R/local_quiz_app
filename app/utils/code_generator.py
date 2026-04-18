"""Generate short unique session codes / player tokens."""
import random
import secrets
import string

_AMBIGUOUS = set("O0I1L")
_POOL = "".join(c for c in string.ascii_uppercase + string.digits if c not in _AMBIGUOUS)


def generate_session_code(length: int = 6) -> str:
    return "".join(random.choices(_POOL, k=length))


def generate_player_token() -> str:
    return secrets.token_urlsafe(16)


def random_avatar(avatars):
    return random.choice(avatars)
