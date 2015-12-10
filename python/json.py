#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import logging

from urchinfs import MetadataExtractor
from urchinfs.generic import GenericDirectoryIndexer, GenericFileMetadataMatcher

DEFAULT_JSON_GLOB = "metadata.json"
JSON_GLOB = "*.json"

def DefaultJsonDirectoryIndexer(GenericDirectoryIndexer):
    """Simple item matcher which returns directories containing a file "metadata.json" """
    name = "json"
    def __init__(self, config):
        super().__init__(self, config, DEFAULT_JSON_GLOB)

def DefaultJsonFileMetadataMatcher(GenericFileMetadataMatcher):
    name = "json-file"
    """Simple metadata matcher which returns the "metadata.json" file as its metadata source"""
    def __init__(self, config):
        super().__init__(self, config, DEFAULT_JSON_GLOB)

class JsonMetadataExtractor(MetadataExtractor):
    name = "json"
    """
    Generic JSON metadata extractor.

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
                        else if type(v) in [list, tuple, set]:
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
