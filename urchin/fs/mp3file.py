#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import os
import logging
from fnmatch import fnmatch

import mutagen
from mutagen.easyid3 import EasyID3

import urchin.fs.default
import urchin.fs.json
import urchin.fs.plugin
import urchin.fs.mp3

MP3_GLOB = "*.mp3"

class Plugin(urchin.fs.plugin.Plugin):
    name = "mp3file"
    def __init__(self):
        super(Plugin, self).__init__(
                indexer=Mp3FileIndexer,
                matcher=urchin.fs.default.DefaultMetadataMatcher,
                extractor=urchin.fs.mp3.Mp3MetadataExtractor,
                merger=urchin.fs.default.DefaultMerger,
                munger=urchin.fs.default.DefaultMunger,
                formatter=Mp3FileFormatter,
                )

class Mp3FileIndexer(urchin.fs.abstract.AbstractFileIndexer):
    name = "mp3file"
    def __init__(self, config):
        super(Mp3FileIndexer, self).__init__(config, MP3_GLOB)

class Mp3FileFormatter(urchin.fs.plugin.Formatter):
    name = "mp3file"
    def __init__(self, config):
        pass
    def format(self, original_name, metadata):
        # reduce single values from sets
        d = {k: list(v)[0] if type(v) == set and len(v) == 1 else v for k,v in metadata.items()}
        return set(["%(tracknumber)s - %(artist)s - %(title)s" % d])
