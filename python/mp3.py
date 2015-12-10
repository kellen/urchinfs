#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from fnmatch import fnmatch
from mutagen.easyid3 import EasyID3

from urchinfs import Formatter
from urchinfs.abstract import AbstractDirectoryIndexer, AbstractFileIndexer, AbstractFileMetadataMatcher

MP3_GLOB = "*.mp3"

def Mp3DirectoryIndexer(AbstractDirectoryIndexer):
    name = "mp3"
    def __init__(self, config):
        super().__init__(self, config, MP3_GLOB)

def Mp3FileIndexer(AbstractFileIndexer):
    name = "mp3-file"
    def __init__(self, config):
        super().__init__(self, config, MP3_GLOB)

def Mp3FileMetadataMatcher(AbstractFileMetadataMatcher):
    name = "mp3"
    def __init__(self, config):
        super().__init__(self, config, MP3_GLOB)

def Mp3MetadataExtractor(MetadataExtractor):
    name = "mp3"
    def __init__(self, config):
        pass
    def extract(self, path):
        id3 = EasyID3(path)
        # FIXME actually get the keys
        print id3.keys()
        raise NotImplementedError()

def Mp3AlbumMetadataMerger(MetadataMerger):
    name = "mp3"
    def __init__(self, config):
        pass
    def merge(self, metadata):
        raise NotImplementedError()

def Mp3DirectoryFormatter(Formatter):
    name = "mp3"
    def format(self, original_name, metadata):
        return original_name

def Mp3FileFormatter(Formatter):
    name = "mp3-file"
    def format(self, original_name, metadata):
        return original_name

