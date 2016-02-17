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
        merged["split"] = set([u"yes"]) if len(merged["artist"]) == 2 else set([u"no"])
        merged["compilation"] = set([u"yes"]) if len(merged["artist"]) > 2 else set([u"no"])
        for e in ensure:
            if not e in merged:
                merged[e] = set([u"????"])
        return merged

class Mp3DirectoryFormatter(urchin.fs.plugin.Formatter):
    name = "mp3"
    def __init__(self, config):
        pass
    def format(self, original_name, metadata):
        # reduce single values from sets
        d = {k: list(v)[0] if type(v) == set and len(v) == 1 else v for k,v in metadata.items()}
        if d["compilation"] == "yes":
            return set(["Compilation - %(date)s - %(album)s" % d])
        elif d["split"] == "yes":
                l = list(d["artist"])
                d["first"] = l[0]
                d["second"] = l[1]
                return set([
                    "%(first)s - %(date)s - with %(second)s - %(album)s" % d,
                    "%(second)s - %(date)s - with %(first)s - %(album)s" % d,
                    ])
        return set(["%(artist)s - %(date)s - %(album)s" % d])
