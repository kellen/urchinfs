#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import os
from fnmatch import fnmatch
from mutagen.easyid3 import EasyID3

from urchin.fs.plugin import Formatter, MetadataExtractor, MetadataMerger
from urchin.fs.abstract import AbstractDirectoryIndexer, AbstractFileIndexer, AbstractFileMetadataMatcher

MP3_GLOB = "*.mp3"

class Mp3DirectoryIndexer(AbstractDirectoryIndexer):
    name = "mp3"
    def __init__(self, config):
        super(Mp3DirectoryIndexer, self).__init__(config, MP3_GLOB)

class Mp3FileIndexer(AbstractFileIndexer):
    name = "mp3-file"
    def __init__(self, config):
        super(Mp3FileIndexer, self).__init__(config, MP3_GLOB)

class Mp3FileMetadataMatcher(AbstractFileMetadataMatcher):
    name = "mp3"
    def __init__(self, config):
        super(Mp3FileMetadataMatcher, self).__init__(config, MP3_GLOB)

class Mp3MetadataExtractor(MetadataExtractor):
    name = "mp3"
    def __init__(self, config):
        pass
    def extract(self, path):
        id3 = EasyID3(path)
        # FIXME actually get the keys
        print id3.keys()
        raise NotImplementedError()

class Mp3AlbumMetadataMerger(MetadataMerger):
    name = "mp3"
    def __init__(self, config):
        pass
    def merge(self, metadata):
        raise NotImplementedError()

class Mp3DirectoryFormatter(Formatter):
    name = "mp3"
    def __init__(self, config):
        pass
    def format(self, original_name, metadata):
        return original_name

class Mp3FileFormatter(Formatter):
    name = "mp3-file"
    def __init__(self, config):
        pass
    def format(self, original_name, metadata):
        return original_name

