import dfuse.fuse;
import std.algorithm, std.conv, std.stdio, std.string;
import std.path, std.array;

class UrchinFSEntry {
    string display_name;
    string[] metadata_sources;
    string[][string] metadata;
}

class UrchinFSResult {
    string[] keys;
    UrchinFSEntry[] entries;
    string[] listing;

    this(string[] keys, UrchinFSEntry[] entries) {
        this.keys = keys;
        this.entries = entries;
        this.listing = [];
    }
}

class UrchinFS : Operations {
    // FIXME certain characters are ignored for collation in UTF-8 locales LC_COLLATION
    static const string FACET_PREFIX = "-";
    static const string OR = FACET_PREFIX ~ "OR";
    enum parsed { KEY, VAL, OR, NONE, DIR }

    // { metadata_key -> { metadata_value -> { display_name -> bool } }}
    // the last nested map is a hack due to no set type in dlang

    UrchinFSEntry[] entries;

    this() {
        // TODO fetch actual data from disk
        UrchinFSEntry easter = new UrchinFSEntry();
        easter.display_name = "Easter Parade (1948)";
        string[][string] easter_md;
        easter_md["year"] = ["1948"];
        easter_md["color"] = ["color"];
        easter.metadata = easter_md;
        entries ~= easter;

        UrchinFSEntry city = new UrchinFSEntry();
        city.display_name = "The Naked City (1948)";
        string[][string] city_md;
        city_md["year"] = ["1948"];
        city_md["color"] = ["black-and-white"];
        city.metadata = city_md;
        entries ~= city;

    }

    // prefix all strings with FACET_PREFIX
    string[] facet_prefix(string[] keys) {
        string[] ret;
        foreach(key; keys) {
            ret ~= (FACET_PREFIX ~ key);
        }
        return ret;
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
    string[] get_listing(UrchinFSEntry[] entries) {
        string[] result;
        foreach(entry; entries) {
            result ~= entry.display_name;
        }
        return result;
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

    // for a split path parts, find the entries matching the specified key-value combinations
    // and return the appropriate directory listing
    string[] get_results(const(char)[][] parts) {
        // strip off any empty leading sections of the path
        int cur = 0;
        while(cur < parts.length && parts[cur].empty) {
            cur++;
        }
        parts = parts[cur..parts.length];

        int index = 0;
        string current_key = null;          // the currently selected key
        string[] current_key_values = [];   // all of the potential values for this key
        string[] current_values = [];       // the currently selected values


        string[][string] state;
        parsed last = parsed.NONE;

        // duplicate all the entries to start with
        UrchinFSEntry[] found = entries.dup;

        while(index < parts.length) {
            bool is_last = index == parts.length-1;
            string part = to!string(parts[index]);

            if(startsWith(part, FACET_PREFIX) && part != OR) {
                // this is a key
                last = parsed.KEY;
                string key = part[FACET_PREFIX.length .. $];

                // fail on duplicate keys
                string[]* key_values = (key in state);
                if(key_values !is null) {
                    stderr.writefln("Duplicate key [%s]", key);
                    throw new FuseException(errno.ENOENT);
                }

                state[key] = [];
                stdout.writefln("key: %s", key);
                found = filter(found, key);
                current_key_values = get_values(found, key);

                if(is_last) {
                    // return the currrent valid values for this key
                    stdout.writefln("key ret: %s", current_key_values);
                    return current_key_values;
                }
                current_key = key;
                current_values = [];
            } else if (last == parsed.VAL && part == OR) {
                // this is an or
                last = parsed.OR;
                stdout.writefln("OR: %s", part);
                
                if(is_last) {
                   return setdiff(current_key_values, current_values);
                }

            } else if(last == parsed.KEY || last == parsed.OR) {
                // this is a value
                last = parsed.VAL;
                stdout.writefln("val: %s", part);

                // this value either does not exist at all
                // or is already selected, so throw an error
                bool not_found = !current_key_values.canFind(part);
                bool already_used = current_values.canFind(part);
                if(not_found || already_used) {
                    stdout.writefln("current key values: %s", current_key_values);
                    stdout.writefln("not found? %s already used? %s", not_found, already_used);
                    throw new FuseException(errno.ENOENT);
                }

                current_values ~= part;

                // append a new array to values, containing the current part
                state[current_key] = state[current_key] ~ part;

                // lookahead, and if the next token is not an OR
                // filter the entries by the current facet.
                if(is_last || (!is_last && to!string(parts[index+1]) != OR)) {
                    found = filter(found, current_key, state[current_key]);
                } 

                if(is_last) {
                    // return the unused keys, OR, and the matching dirs
                    string[] ret = get_listing(found);
                    stdout.writefln("val ret: %s", current_key_values);
                    // FIXME
                    return ret ~ facet_prefix(setdiff(get_keys(found), state.keys)) ~ OR;
                }
            } else {
                // this must be a dir
                last = parsed.DIR;
                stdout.writefln("dir: %s", part);

                if(is_last) {
                    // this is a symlink... don't use this as a return val???
                    string[] ret;
                    ret ~= "FIXME";
                    return ret;
                }
            }
            index++;
            stdout.writefln("state: %-(%s -> %s%)", state);
        }
        stdout.writeln("----");
        // FIXME need to return all potential keys, prefixed with FACET_PREFIX
        // FIXME as well as all entries
        return get_listing(found) ~ facet_prefix(get_keys(found)) ~ "+" ~ "^";
    }

    override void getattr(const(char)[] path, ref stat_t s) {
        string[] results = get_results(path.split("/"));

        // FIXME ; end dirs need to be symlinks
        s.st_mode = S_IFDIR | octal!755;
        s.st_size = 0;
        return;

        /*
        if (path == "/") {
            s.st_mode = S_IFDIR | octal!755;
            s.st_size = 0;
            return;
        }
        if (path.among("/a", "/b")) {
            s.st_mode = S_IFREG | octal!644;
            s.st_size = 42;
            return;
        }
        throw new FuseException(errno.ENOENT);
        */
    }

    override string[] readdir(const(char)[] path) {
        return get_results(path.split("/"));
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
