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
    static const string FACET_PREFIX = "+";
    static const string OR = FACET_PREFIX ~ "OR";
    enum parsed { KEY, VAL, OR, NONE, DIR }

    // { metadata_key -> { metadata_value -> { display_name -> bool } }}
    // the last nested map is a hack due to no set type in dlang

    bool[string][string][string] metadata_cache;
    UrchinFSEntry[] entries;

    this() {
        // TODO fetch actual data from disk
        bool[string] year_dirs_48;
        year_dirs_48["Easter Parade"] = true;
        year_dirs_48["Force of Evil"] = true;

        bool[string] year_dirs_12;
        year_dirs_12["Skyfall"] = true;
        year_dirs_12["Rust and Bone"] = true;

        bool[string][string] years;
        years["1948"] = year_dirs_48;
        years["2012"] = year_dirs_12;

        metadata_cache["year"] = years;
    }

    string[] get_results(const(char)[][] parts) {
        // strip off any empty leading sections of the path
        int cur = 0;
        while(cur < parts.length && parts[cur].empty) {
            cur++;
        }
        parts = parts[cur..parts.length];

        int index = 0;
        string[] keys;
        string[][] values;
        parsed last = parsed.NONE;

        while(index < parts.length) {
            string part = to!string(parts[index]);

            if(startsWith(part, FACET_PREFIX) && part != OR) {
                // this is a key
                last = parsed.KEY;
                keys ~= part;
                stdout.writefln("key: %s", part);
            } else if (last == parsed.VAL && part == OR) {
                // this is an or
                last = parsed.OR;
                stdout.writefln("OR: %s", part);
            } else if(last == parsed.KEY || last == parsed.OR) {
                // this is a value
                last = parsed.VAL;
                stdout.writefln("val: %s", part);
                if(last == parsed.KEY) {
                    string[]

                        // HERE
                    values ~= []
                } else {
                    values[
                }
            } else {
                // this must be a dir
                last = parsed.DIR;
                stdout.writefln("dir: %s", part);
            }
            index++;
        }
        stdout.writeln("----");
        return [];
    }

    /*
    string[] get_results(const(char)[][] parts, UrchinFSResult result) {
        // possible paths showing up here:
        // parts.length     path
        // 0                /
        // 1                /key
        // 2                /key/value
        // 3                /key/value/key
        // 3                /key/value1/+OR
        // 4                /key/value1/+OR/value2
        // TODO tests: path/with///////multiple/slashes/
        // TODO tests: / <- how is root handled?
        // TODO tests: /key/value/NONEXISTENTKEY/
        // TODO tests: /key/value-with-no-results/key/ ???
        // TODO tests: /dir <- not a key


        if(parts.empty) {
            // FIXME generate the result listing
            return result;
        }

        bool has_value = parts.length > 1;
        bool has_or = parts.length > 2 && parts[2] == OR;

        string key = parts[0];
        bool[string][string] vals = (parts in metadata_cache);
        if(vals !is null) {
            // this was a valid key



            if(has_value) {
                value = parts[1];
                // there is a value given on the path
                bool[string] dirs = (value in vals);
                if(dirs !is null) {
                    // the value existed in the metadata map
                    // find the 


                    if(parts.length == 2) {
                        // this was the last component
                    }

                } else {
                    if(parts.length == 2) {
                        // the value did not exist and this is
                        // the last part of the directory path
                        return [];
                    }
                }
            } else {
                // FIXME filter out the impossible keys somehow
                return vals.keys;
            }
        }
        // this was not a valid key
        throw new FuseException(errno.ENOENT);
    }
    */

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
