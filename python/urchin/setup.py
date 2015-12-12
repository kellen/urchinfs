#!/usr/bin/env python

from distutils.core import setup

setup(
        name='urchin-tmdb',
        version='0.1',
        description='The Movie DB JSON-content fetcher',
        author='Kellen Dye',
        author_email='kellen@cretin.net',
        url='https://github.com/kellen/urchin-tmdb/',
        packages=['urchin-tmdb'],
        license='Public Domain',
        install_requires=['tmdb3', 'googlesearch', 'requests']
        )
