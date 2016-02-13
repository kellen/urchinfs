#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import os
import logging
import pdb
from fnmatch import fnmatch

import mutagen
from mutagen.easyid3 import EasyID3

import urchin.fs.default
import urchin.fs.json
import urchin.fs.plugin

MP3_GLOB = "*.mp3"

class Plugin(urchin.fs.plugin.Plugin):
    name = "mp3"
    def __init__(self):
        super(Plugin, self).__init__(
                indexer=Mp3DirectoryIndexer,
                matcher=Mp3FileMetadataMatcher,
                extractor=Mp3MetadataExtractor,
                merger=Mp3AlbumMetadataMerger,
                munger=urchin.fs.default.DefaultMunger,
                formatter=Mp3DirectoryFormatter,
                )

class Mp3DirectoryIndexer(urchin.fs.abstract.AbstractDirectoryIndexer):
    name = "mp3"
    def __init__(self, config):
        super(Mp3DirectoryIndexer, self).__init__(config, MP3_GLOB)

class Mp3FileIndexer(urchin.fs.abstract.AbstractFileIndexer):
    name = "mp3-file"
    def __init__(self, config):
        super(Mp3FileIndexer, self).__init__(config, MP3_GLOB)

class Mp3FileMetadataMatcher(urchin.fs.abstract.AbstractFileMetadataMatcher):
    name = "mp3"
    def __init__(self, config):
        super(Mp3FileMetadataMatcher, self).__init__(config, MP3_GLOB)

class Mp3MetadataExtractor(urchin.fs.plugin.MetadataExtractor):
    name = "mp3"
    def __init__(self, config):
        pass
    def extract(self, path):
        md = {}
        try:
            id3 = EasyID3(path)
            for key in id3.keys():
                try:
                    val = id3[key]
                    md[key] = set(val)
                except mutagen.easyid3.EasyID3KeyError:
                    continue # ignore invalid id3s
        except mutagen.id3.ID3NoHeaderError:
            pass # file has no id3
        return md

class Mp3AlbumMetadataMerger(urchin.fs.plugin.MetadataMerger):
    name = "mp3"
    def __init__(self, config):
        pass
    def merge(self, metadata):
        merged = dict()
        ensure = ["date", "album", "artist"]
        ignore = ["tracknumber", "title", "length"]
        for source,d in metadata.items():
            for k,v in d.items():
                if k in ignore:
                    continue
                if k not in merged:
                    merged[k] = v
                else:
                    merged[k].update(v)
        merged["split"] = "yes" if len(merged["artist"]) == 2 else "no"
        merged["compilation"] = "yes" if len(merged["artist"]) > 2 else "no"

        for e in ensure:
            if not e in merged:
                merged[e] = set(["????"])
        return merged

class Mp3DirectoryFormatter(urchin.fs.plugin.Formatter):
    name = "mp3"
    def __init__(self, config):
        pass
    def format(self, original_name, metadata):
        d = metadata.copy()
        #for k in d:
        #    if type(d[k]) == list and len(d[k]) == 1:
        #        d[k] = d[k][0]
        d = {k: v[0] if type(v) == list and len(v) == 1 else v for k,v in d.items()}
        if metadata["compilation"] == "yes":
            return set(["Compilation - %(date)s - %(album)s" % d])
        else:
            if metadata["split"] == "yes":
                d["first"] = metadata["artist"][0]
                d["second"] = metadata["artist"][1]
                return set([
                    "%(first)s - %(date)s - split with %(second) - %(album)s" % d,
                    "%(second)s - %(date)s - split with %(first) - %(album)s" % d,
                    ])
            else:
                return set(["%(artist)s - %(date)s - %(album)s" % d])
        return original_name

# TODO
class Mp3FileFormatter(urchin.fs.plugin.Formatter):
    name = "mp3-file"
    def __init__(self, config):
        pass
    def format(self, original_name, metadata):
        return original_name


# TODO define multiple plugins here? or make new module?
"""
class Plugin(urchin.fs.plugin.Plugin):
    name = "mp3-file"
    def __init__(self):
        super(Plugin, self).__init__(
                indexer=Mp3FileIndexer,
                matcher=urchin.fs.default.DefaultMetadataMatcher,
                extractor=Mp3MetadataExtractor,
                merger=urchin.fs.default.DefaultMerger,
                munger=urchin.fs.default.DefaultMunger,
                formatter=urchin.fs.default.DefaultFormatter
                )
"""
