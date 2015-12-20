import urchin.fs.default
import urchin.fs.json
import urchin.fs.plugin
import logging

class Plugin(urchin.fs.plugin.Plugin):
    name = "tmdb"
    def __init__(self):
        super(Plugin, self).__init__(
                indexer=urchin.fs.json.DefaultJsonDirectoryIndexer,
                matcher=urchin.fs.json.DefaultJsonFileMetadataMatcher,
                extractor=urchin.fs.json.BasicJsonMetadataExtractor,
                merger=urchin.fs.default.DefaultMerger,
                munger=TMDBMetadataMunger,
                formatter=urchin.fs.default.DefaultFormatter
                )

class TMDBMetadataMunger(urchin.fs.plugin.MetadataMunger):
    name = "tmdb"
    def __init__(self, config):
        pass
    def mung(self, metadata):
        out = {}
        copy_keys = ["title", "runtime", "original_language"]
        for key in copy_keys:
            if key in metadata:
                val = metadata[key]
                if type(val) in urchin.fs.json.stringable_types:
                    out[key] = set([unicode(val)])
                else:
                    logging.error("can't convert to string from type %s for key %s" % (type(val)), key)
        extract_name = ["genres", ]
        # the key in metadata -> the value to extract from the object
        extract = {"production_countries": "iso_3166_1"}
        for key in extract_name:
            extract[key] = "name"

        for key,obj_key in extract.iteritems():
            out[key] = set()
            for val_obj in metadata[key]:
                if type(val_obj) != dict:
                    logging.error("can't extract from non-dict for key '%s'" % key)
                else:
                    try:
                        val = val_obj[obj_key]
                        if type(val) in urchin.fs.json.stringable_types:
                            out[key].add(unicode(val))
                        else:
                            logging.error("can't convert to string from type %s" % type(val))
                    except KeyError:
                        logging.error("object with key '%s' has no key '%s'" % (key, obj_key))
        return out
