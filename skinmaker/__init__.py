"""Skin maker: turn a character description (and optional reference image) into an
animated widget skin using an image-generation API. See pipeline.py and providers.py;
command line: python -m skinmaker --help"""
from .pipeline import ROW_NAMES, Cancelled, assemble, generate_rows, make_skin, preview  # noqa: F401
from .providers import DEFAULT_PROVIDER, PROVIDERS, get_key, get_provider, set_key  # noqa: F401
