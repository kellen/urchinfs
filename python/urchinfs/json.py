#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import logging
import types

from plugin import MetadataExtractor
from abstract import AbstractDirectoryIndexer, AbstractFileMetadataMatcher

DEFAULT_JSON_GLOB = "metadata.json"
JSON_GLOB = "*.json"

class DefaultJsonDirectoryIndexer(AbstractDirectoryIndexer):
    """Simple item matcher which returns directories containing a file "metadata.json" """
    name = "json"
    def __init__(self, config):
        super().__init__(self, config, DEFAULT_JSON_GLOB)

class DefaultJsonFileMetadataMatcher(AbstractFileMetadataMatcher):
    name = "json"
    """Simple metadata matcher which returns the "metadata.json" file as its metadata source"""
    def __init__(self, config):
        super().__init__(self, config, DEFAULT_JSON_GLOB)

class JsonMetadataExtractor(MetadataExtractor):
    name = "json"
    """
    Abstract JSON metadata extractor.

    Converts non-string keys and values to strings if straightforward.
    Values must be lists or single values, otherwise they are ignored.
    """
    stringable_types = [str, unicode, int, long, float, bool, types.NoneType]
    def __init__(self, config):
        pass
    def extract(self, path):
        logging.debug("extracting metadata from '%s' as json" % path)
        md = dict()
        with open(path, 'r') as file:
            source = json.load(file)
            if type(source) == dict:
                for k,v in d.iteritems():
                    if type(k) in stringable_types:
                        key = unicode(k)
                        md[key] = []
                        if type(v) in stringable_types:
                            md[key].append(unicode(v))
                        elif type(v) in [list, tuple, set]:
                            for val in v:
                                if type(val) in stringable_types:
                                    md[key].append(unicode(val))
                                else:
                                    logging.warning("Value [%s] not cleanly convertable to string, ignoring." % val)
                        else:
                            logging.warning("Value [%s] not cleanly convertable to string, ignoring." % v)
                    else:
                        logging.warning("Key [%s] not cleanly convertable to string, ignoring." % k)
            else:
                logging.error("Found metadata in '%s', but could not parse file into a dict" % path)
