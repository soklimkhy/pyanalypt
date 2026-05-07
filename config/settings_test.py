from .settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Disable password hashing to speed up tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Use in-process cache — no Redis needed for tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# allauth's account.0006 is a data migration that queries auth_user before
# the custom User table is ready in SQLite, causing a transaction error.
# core.0003 cross-depends on both account and socialaccount migrations.
# Bypassing all three lets Django use syncdb (plain CREATE TABLE) instead.
MIGRATION_MODULES = {
    "account": None,
    "socialaccount": None,
    "core": None,
    "token_blacklist": None,   # 0003 data migration queries auth_user via raw SQL
}
