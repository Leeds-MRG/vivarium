#!/usr/bin/env python
# ~/ceam/setup.py

from setuptools import setup, find_packages


setup(name='ceam',
        version='0.1',
        packages=find_packages(),
        install_requires=[
            'pandas',
            'numpy',
            'scipy',
            'joblib',
            'mmh3'
        ]
     )


# End.
