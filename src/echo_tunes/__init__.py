"""echo-tunes: a self-hosted Alexa skill that plays YouTube Music on your Echo."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("echo-tunes")
except PackageNotFoundError:  # running from a source checkout without installing
    __version__ = "0.0.0"
