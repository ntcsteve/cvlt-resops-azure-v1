# Compatibility shim – all real config lives in pyproject.toml. This exists only
# so `pip install -e .` works on older pip (pre-PEP-660) via legacy `develop`.
from setuptools import setup

setup()
