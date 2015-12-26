import urchin.fs.default
import urchin.fs.json
import urchin.fs.plugin
import logging
from datetime import datetime

class Plugin(urchin.fs.plugin.Plugin):
    name = "tmdb"
    def __init__(self):
        super(Plugin, self).__init__(
                indexer=urchin.fs.json.DefaultJsonDirectoryIndexer,
                matcher=urchin.fs.json.DefaultJsonFileMetadataMatcher,
                extractor=urchin.fs.json.BasicJsonMetadataExtractor,
                merger=urchin.fs.default.DefaultMerger,
                munger=TMDBMetadataMunger,
                formatter=TMDBFormatter
                )

class TMDBMetadataMunger(urchin.fs.plugin.MetadataMunger):
    name = "tmdb"
    def __init__(self, config):
        pass
    def mung(self, metadata):
        out = {}
        copy_keys = ["original_title", "title", "runtime", "original_language", "imdb_id"]
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
        # director
        crew_key = "crew"
        if crew_key in metadata:
            directors = set()
            for crew in metadata[crew_key]:
                if "job" in crew and crew["job"] == "Director":
                    directors.add(crew["name"])
            if directors:
                out["director"] = directors

        # year
        date_key = "release_date"
        if date_key in metadata:
            years = set()
            date = metadata[date_key]
            try:
                d = datetime.strptime(date, "%Y-%m-%d")
                years.add(unicode(d.year))
            except ValueError:
                logging.debug("Could not parse year from [%s]" % date)
            if years:
                out["year"] = years
        return out

class TMDBFormatter(urchin.fs.plugin.Formatter):
    name = "tmdb"
    def __init__(self, config):
        pass
    def format(self, original_name, metadata):
        # everything is wraped in sets
        title = None if "title" not in metadata else ", ".join(metadata["title"])
        year = None if "year" not in metadata else ", ".join(metadata["year"])
        alts = None if "original_title" not in metadata else ", ".join(metadata["original_title"])
        director = None if "director" not in metadata else ", ".join(metadata["director"])

        parens = ", ".join([p for p in [director, year] if p is not None])

        formatted_name = "%s%s%s" % (title,
                "" if not alts or alts == title else " (%s)" % alts,
                "" if not parens else " (%s)" % parens)
        return set([formatted_name])
