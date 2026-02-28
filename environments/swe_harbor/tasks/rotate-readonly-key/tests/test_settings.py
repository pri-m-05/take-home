from hc.settings import *

# Remove the missing app from Django app loading
INSTALLED_APPS = tuple(app for app in INSTALLED_APPS if app != "hc.logs")

# Disable the broken custom logging config
LOGGING_CONFIG = None
LOGGING = {"version": 1, "disable_existing_loggers": False}

# Faster / simpler tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
