from hc.settings import *

INSTALLED_APPS = tuple(app for app in INSTALLED_APPS if app != "hc.logs")

LOGGING_CONFIG = None
LOGGING = {"version": 1, "disable_existing_loggers": False}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"