import dfuse.fuse;
import std.algorithm, std.conv, std.stdio, std.string;
import std.path, std.array;

class UrchinFSEntry {
    string display_name;
    string[] metadata_sources;
    string[][string] metadata;
}

class UrchinFSResult {
    string name;
    int mode;
    int size = 0;

    this(string name, int mode) immutable {
        this.name = name;
        this.mode = mode;
    }
}

class UrchinFS : Operations {
    static const string AND = "^";
    static immutable UrchinFSResult AND_DIR = new immutable UrchinFSResult("^", S_IFDIR | octal!755);
    static const string OR = "+";
    static immutable UrchinFSResult OR_DIR = new immutable UrchinFSResult("+", S_IFDIR | octal!755);
    enum parsed { KEY, VAL, AND, OR, NONE, DIR }

    // { metadata_key -> { metadata_value -> { display_name -> bool } }}
    // the last nested map is a hack due to no set type in dlang

    UrchinFSEntry[] entries;

    this() {
        // TODO fetch actual data from disk
        UrchinFSEntry easter = new UrchinFSEntry();
        easter.display_name = "Easter Parade (1948, color)";
        string[][string] easter_md;
        easter_md["year"] = ["1948"];
        easter_md["color"] = ["color"];
        easter.metadata = easter_md;
        entries ~= easter;

        UrchinFSEntry city = new UrchinFSEntry();
        city.display_name = "The Naked City (1948, bw)";
        string[][string] city_md;
        city_md["year"] = ["1948"];
        city_md["color"] = ["black-and-white"];
        city.metadata = city_md;
        entries ~= city;

        UrchinFSEntry vanish = new UrchinFSEntry();
        vanish.display_name = "The Lady Vanishes (1938, bw)";
        string[][string] vanish_md;
        vanish_md["year"] = ["1938"];
        vanish_md["color"] = ["black-and-white"];
        vanish.metadata = vanish_md;
        entries ~= vanish;

        UrchinFSEntry kiss = new UrchinFSEntry();
        kiss.display_name = "Kiss Me Deadly (1955, bw)";
        string[][string] kiss_md;
        kiss_md["year"] = ["1955"];
        kiss_md["color"] = ["black-and-white"];
        kiss.metadata = kiss_md;
        entries ~= kiss;
    }

    // get all of the valid keys for the given entries
    string[] get_keys(UrchinFSEntry[] entries) {
        bool[string] keys;
        foreach(entry; entries) {
            foreach(string key, string[] v; entry.metadata) {
                keys[key] = true;
            }
        }
        return keys.keys;
    }

    // get all of the values specified for key in entries
    string[] get_values(UrchinFSEntry[] entries, string key) {
        bool[string] values;
        foreach(entry; entries) {
            string[]* key_values_ptr = (key in entry.metadata);
            if(key_values_ptr !is null) {
                string[] key_values = *key_values_ptr;
                foreach(val; key_values) {
                    values[val] = true;
                }
            }
        }
        return values.keys;
    }

    // get all of the display names for the given entries
    immutable(UrchinFSResult)[] get_listing(UrchinFSEntry[] entries) {
        immutable(UrchinFSResult)[] result;
        foreach(entry; entries) {
            // FIXME ; end dirs need to be symlinks
            result ~= new immutable UrchinFSResult(entry.display_name, S_IFDIR | octal!755);
        }
        return result;
    }

    // get all the listings from the given result
    string[] get_listing(immutable(UrchinFSResult)[] results) {
        string[] listing;
        foreach(result; results) {
            listing ~= result.name;
        }
        return listing;
    }

    // fitler the entries which have the given key
    UrchinFSEntry[] filter(UrchinFSEntry[] entries, string key) {
        UrchinFSEntry[] result;
        foreach(i, entry; entries) {
            string[]* key_values_ptr = (key in entry.metadata);
            if(key_values_ptr !is null) {
                result ~= entry;
            }
        }
        return result;
    }

    // filter the entries by the given key and values
    // if an entry has the key and has one of the values, it is retained
    UrchinFSEntry[] filter(UrchinFSEntry[] entries, string key, string[] values) {
        UrchinFSEntry[] result;
        foreach(i, entry; entries) {
            bool keep = false;

            string[]* key_values_ptr = (key in entry.metadata);
            if(key_values_ptr !is null) {
                string[] key_values = *key_values_ptr;
                foreach(j, val; key_values) {
                    foreach(value; values) {
                        if(val == value) {
                            keep = true;
                            break;
                        }
                    }
                    if(keep) {
                        break;
                    }
                }
            }

            if(keep) {
                result ~= entry;
            }
        }
        return result;
    }

    // set difference
    string[] setdiff(string[] set, string[] minus) {
        // clear way to do this
        bool[string] map;
        foreach(val; set) {
            map[val] = true;
        }
        foreach(val; minus) {
            map.remove(val);
        }
        return map.keys;
    }

    immutable(UrchinFSResult)[] to_result(string[] listing) {
        immutable(UrchinFSResult)[] result;
        foreach(entry; listing) {
            result ~= new immutable UrchinFSResult(entry, S_IFDIR | octal!755);
        }
        return result;
    }

    // for a split path parts, find the entries matching the specified key-value combinations
    // and return the appropriate directory listing
    immutable(UrchinFSResult)[] get_results(const(char)[][] parts) {
        // strip off any empty leading sections of the path
        int cur = 0;
        while(cur < parts.length && parts[cur].empty) {
            cur++;
        }
        parts = parts[cur..parts.length];
        stdout.writefln("parts: %s", parts);

        // start with all entries
        UrchinFSEntry[] found = entries.dup;

        // root dir
        if(parts.length == 0) {
            return get_listing(found) ~ AND_DIR;
        }

        string[] current_valid_keys = get_keys(found);  // the valid keys for the current entries
        string[] current_valid_values = [];             // the valid values for the current entires + key
        string current_key = null;                      // the currently selected key

        // FIXME see if state can be simplified/ignored
        // FIXME see if we can cache anything
        string[][string] state;
        parsed last = parsed.NONE;

        int index = 0;
        while(index < parts.length) {
            bool is_last = index == parts.length-1;
            string part = to!string(parts[index]);

            if(part == AND) {
                last = parsed.AND;
                current_key = null;
                current_valid_values = [];

                current_valid_keys = setdiff(get_keys(found), state.keys);
                if(is_last) {
                    return to_result(current_valid_keys);
                }
            } else if (last == parsed.AND) {
                last = parsed.KEY;
                string key = part;

                // fail on invalid keys 
                if(!current_valid_keys.canFind(key)) {
                    stderr.writefln("Invalid key [%s]", key);
                    throw new FuseException(errno.ENOENT);
                }
                // fail on duplicate keys
                if((key in state) !is null) {
                    stderr.writefln("Duplicate key [%s]", key);
                    throw new FuseException(errno.ENOENT);
                }

                current_key = key;
                current_valid_keys = setdiff(current_valid_keys, [key]);
                state[key] = [];
                found = filter(found, key);

                current_valid_values = get_values(found, key);
                if(is_last) {
                    return to_result(current_valid_values);
                }
            } else if (last == parsed.VAL && part == OR) {
                last = parsed.OR;
                if(is_last) {
                    return to_result(current_valid_values);
                }
            } else if(last == parsed.KEY || last == parsed.OR) {
                last = parsed.VAL;
                string value = part;

                // fail on not found or already-used values
                if(!current_valid_values.canFind(value)) {
                    stderr.writefln("Invalid value [%s]", value);
                    throw new FuseException(errno.ENOENT);
                }

                // update the currently-valid values list
                current_valid_values = setdiff(current_valid_values, [value]);

                // append a new array to values, containing the current value
                state[current_key] = state[current_key] ~ value;

                // lookahead, and if the next token is _not_ an OR,
                // filter the entries by the current facet
                if(is_last || (!is_last && to!string(parts[index+1]) != OR)) {
                    found = filter(found, current_key, state[current_key]);
                } 

                if(is_last) {
                    immutable(UrchinFSResult)[] ret = get_listing(found);
                    // add AND and OR if appropriate
                    if(current_valid_values.length > 0) {
                        ret ~= OR_DIR;
                    }
                    if(current_valid_keys.length > 0) {
                        ret ~= AND_DIR;
                    }
                    return ret;
                }
            } else {
                // FIXME this must return something to indicate that it should
                // FIXME be a symlink
                last = parsed.DIR;
                if(is_last) {
                    immutable(UrchinFSResult)[] ret;
                    ret ~= new immutable UrchinFSResult("FIXME", S_IFDIR | octal!755);
                    return ret;
                }
            }
            index++;
            stdout.writefln("state: %-(%s -> %s%)", state);
        }
        throw new FuseException(errno.ENOENT);
    }

    override void getattr(const(char)[] path, ref stat_t s) {
        // FIXME add current dir "." to get_results
        immutable(UrchinFSResult)[] results = get_results(path.split("/"));
        // FIXME ; end dirs need to be symlinks
        s.st_mode = S_IFDIR | octal!755;
        s.st_size = 0;
        return;
    }

    override string[] readdir(const(char)[] path) {
        return get_listing(get_results(path.split("/")));
    }
}

int main(string[] args) {
    if (args.length != 2) {
        stderr.writeln("urchinfs <MOUNTPOINT>");
        return -1;
    }
    stdout.writeln("mounting urchinfs");

    auto fs = new Fuse("UrchinFS", true, false);
    fs.mount(new UrchinFS(), args[1], []);

    return 0;
}
