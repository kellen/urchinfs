#!/usr/bin/env python

from distutils.core import setup

setup(
        name='urchin',
        version='0.1.0',
        description='faceted-search FUSE filesystem and utilities',
        author='Kellen Dye',
        author_email='kellen@cretin.net',
        url='https://github.com/kellen/urchinfs/',
        packages=['urchin', 'urchin.fs', 'urchin.tmdb'],
        license='Public Domain',
        install_requires=['googlesearch', 'requests', 'fuse']
        )
