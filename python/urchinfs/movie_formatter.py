#!/usr/bin/env python
# -*- coding: utf-8 -*-

from urchinfs import Formatter

# FIXME dunno wtf i was doing here, fix it later.
class MovieFormatter(Formatter):
    def format(self, original_name, metadata):
        english_countries = ["USA", "Canada", "Australia", "UK"]
        md = {"title": None, "director": None, "year": None }
        for key in md:
            md[key] = ", ".join(string_generator(metadata[key])) if key in metadata else None
        if "country" in metadata:
            country = metadata["country"]
            english_found = False
            if type(country) in stringable_types:
                if unicode(country) in english_countries:
                    english_found = True
            else:
                for c in country:
                    if unicode(c) in english_countries:
                        english_found = True
            if not english_found:
                if "alternative-title" in metadata:
                    alt = metadata["alternative-title"]
                    english_alt_found = False
                    for a in alt:
                        if type(a) == dict:
                            if "country" in a:
                                c = unicode(a["country"])
                                startswith = ["english"] + english_countries
                                for s in startswith:
                                    if c.startswith(s):
                                        if "title" in a:
                                            md["original_title"] = md["title"]
                                            md["title"] = a["title"]
                                            english_alt_found = True
                                if english_alt_found:
                                    break
        if md["title"] is None:
            return original_name
        t = md["title"]
        if "original_title" in md:
            t = t + "(" + md["original_title"] + ")"
        if md["director"] or md["year"]:
            t = t + " ("
        if md["director"]:
            t = t + md["director"]
        if md["director"] and md["year"]:
            t = t + ", "
        if md["year"]:
            t = t + md["year"]
        if md["director"] or md["year"]:
            t = t + ")"
        return t
