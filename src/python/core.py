#!/usr/bin/env python

# -------------------------------------------------------------------
# Copyright (c) 2009 Matt Giuca
# This software and its accompanying documentation is licensed under the
# MIT License.
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
# -------------------------------------------------------------------

# TemplateFS - A Simple Python Fuse Example
# This file system does absolutely nothing, but it's a complete stubbed-out
# file system ready for whatever implementation is desired.
#
# Fuse lets you easily create your own filesystems which run entirely in user
# mode and with normal user permissions.
# This example presents a simple file system.
# You mount it by directly running this file.
#
# Usage:
#     templatefs.py MOUNTPOINT
#     templatefs.py MOUNTPOINT -o xyz=VALUE
#     templatefs.py arg1 arg2 .. MOUNTPOINT argn arg(n+1) ...
# To unmount:
#     fusermount -u MOUNTPOINT
#
# Use `tail -f LOG` to read the log in real-time (as it is written).
# Also, mount with `./templatefs.py MOUNTPOINT -d` to have FUSE print out its own
# debugging messages (which are in some cases more, and some cases less useful
# than mine).
#
# Issues with this template
# =========================
# I have tried to stub out all methods which Fuse will call (including
# undocumented ones, some of which are very important).
# I have not yet done the following:
# - getxattr
# - listxattr
# - setxattr
# - removexattr
# - lock
# - bmap
#
# Note that some of the data in this document come from experimentation.
# There is no guarantee that later versions and implementations of FUSE
# will behave the same way as the tested version.
#

# Notes on implementing this template
# ===================================
# The comments in this file are intended to be instructional, and may end up
# becoming proper documentation.
#
# All methods log their inputs to a file called "LOG" by default (in the
# current directory), so you can experiment with the filesystem and
# note exactly how all the methods get called.
#
# Most methods just return -errno.EOPNOTSUPP (Operation not supported). If you
# plan to implement a method, you could change the stub to -errno.ENOSYS
# (Function not implemented). If your system actually doesn't support an
# operation, leave it as -errno.EOPNOTSUPP.

# Notes on working out all the methods to implement
# =================================================
# Python Fuse is fairly poorly documented. The documentation is here:
# http://apps.sourceforge.net/mediawiki/fuse/index.php?
#   title=FUSE_Python_Reference
# But it's very scarce in some cases.
#
# A better bet is to look at the C reference, but it's very scarce too, and
# you have to figure out how it applies to Python (not always obvious):
# http://fuse.sourceforge.net/doxygen/structfuse__operations.html
#
# So finally, I turned to the source code. This is also very difficult to
# understand because the functions aren't explicitly defined anywhere. The
# only places they are actually defined is in the C wrapping code, which has a
# handler for each Fuse C function, and calls a Python function object. From
# here, you can tell what it's marshalling between C and Python.
# This is found in /fuseparts/_fusemodule.c in the source tree.
# Most functions just copy over their arguments into Python, but some are
# tricky (such as open).

import fuse

import os
import stat
import errno
import datetime
import time
import calendar
import logging

# First, we define a class deriving from fuse.Stat. This object is used to
# describe a file in our virtual file system.
# This class is rather large, but the concept is really simple (there's just a
# lot of code here to make construction really easy).
# All you have to do is present an object with the following fields, all ints:
#   st_mode:
#       Should be stat.S_IFREG or S_IFDIR OR'd with a normal Unix permission
#       flag, such as 644.
#   st_ino, st_dev:
#       0. Ignored, but required.
#   st_nlink:
#       Number of hard links to this file. For files, usually 1. For
#       directories, usually 2 + number of immediate subdirs (one for parent,
#       one for self, one for each child).
#   st_uid, st_gid:
#       uid/gid of file owner.
#   st_size:
#       File size in bytes.
#   st_atime, st_mtime, st_ctime:
#       File access times, in seconds since the epoch, UTC time. Last access
#       time, modification time, stat change time, respectively.
class Stat(fuse.Stat):
    """
    A Stat object. Describes the attributes of a file or directory.
    Has all the st_* attributes, as well as dt_atime, dt_mtime and dt_ctime,
    which are datetime.datetime versions of st_*time. The st_*time versions
    are in epoch time.
    """
    # Filesize of directories, in bytes.
    DIRSIZE = 4096

    # We can define __init__ however we like, because it's only called by us.
    # But it has to have certain fields.
    def __init__(self, st_mode, st_size, st_nlink=1, st_uid=None, st_gid=None,
            dt_atime=None, dt_mtime=None, dt_ctime=None):
        """
        Creates a Stat object.
        st_mode: Required. Should be stat.S_IFREG or stat.S_IFDIR ORed with a
            regular Unix permission value like 0644.
        st_size: Required. Size of file in bytes. For a directory, should be
            Stat.DIRSIZE.
        st_nlink: Number of hard-links to the file. Regular files should
            usually be 1 (default). Directories should usually be 2 + number
            of immediate subdirs (one from the parent, one from self, one from
            each child).
        st_uid, st_gid: uid/gid of file owner. Defaults to the user who
            mounted the file system.
        st_atime, st_mtime, st_ctime: atime/mtime/ctime of file.
            (Access time, modification time, stat change time).
            These must be datetime.datetime objects, in UTC time.
            All three values default to the current time.
        """
        self.st_mode = st_mode
        self.st_ino = 0         # Ignored, but required
        self.st_dev = 0         # Ignored, but required
        # Note: Wiki says st_blksize is required (like st_dev, ignored but
        # required). However, this breaks things and another tutorial I found
        # did not have this field.
        self.st_nlink = st_nlink
        if st_uid is None:
            st_uid = os.getuid()
        self.st_uid = st_uid
        if st_gid is None:
            st_gid = os.getgid()
        self.st_gid = st_gid
        self.st_size = st_size
        now = datetime.datetime.utcnow()
        self.dt_atime = dt_atime or now
        self.dt_mtime = dt_mtime or now
        self.dt_ctime = dt_ctime or now

    def _get_dt_atime(self):
        return self.epoch_datetime(self.st_atime)
    def _set_dt_atime(self, value):
        self.st_atime = self.datetime_epoch(value)
    dt_atime = property(_get_dt_atime, _set_dt_atime)

    def _get_dt_mtime(self):
        return self.epoch_datetime(self.st_mtime)
    def _set_dt_mtime(self, value):
        self.st_mtime = self.datetime_epoch(value)
    dt_mtime = property(_get_dt_mtime, _set_dt_mtime)

    def _get_dt_ctime(self):
        return self.epoch_datetime(self.st_ctime)
    def _set_dt_ctime(self, value):
        self.st_ctime = self.datetime_epoch(value)
    dt_ctime = property(_get_dt_ctime, _set_dt_ctime)

    @staticmethod
    def datetime_epoch(dt):
        """
        Converts a datetime.datetime object which is in UTC time
        (as returned by datetime.datetime.utcnow()) into an int, which represents
        the number of seconds since the system epoch (also in UTC time).
        """
        # datetime.datetime.timetuple converts a datetime into a time.struct_time.
        # calendar.timegm converts a time.struct_time into epoch time, without
        # modifying for time zone (so UTC time stays in UTC time, unlike
        # time.mktime).
        return calendar.timegm(dt.timetuple())
    @staticmethod
    def epoch_datetime(seconds):
        """
        Converts an int, the number of seconds since the system epoch in UTC
        time, into a datetime.datetime object, also in UTC time.
        """
        return datetime.datetime.utcfromtimestamp(seconds)

# Almost all that is required is the definition of a class deriving from
# fuse.Fuse, and implementation of a bunch of methods.
class TemplateFS(fuse.Fuse):
    """
    A Fuse filesystem object. Implements methods which are called by the Fuse
    system as a result of the operating system requesting filesystem
    operations on places where this file system is mounted.

    Unless otherwise documented, all of these methods return an int.
    This should be 0 on success, or the NEGATIVE of an errno value on failure.
    For example, to report "no such file or directory", methods return
    -errno.ENOENT. See the errno manpage for a list of errno values. (Though
    note that Python's errno is slightly different; see help(errno)).
    Methods should return errno.EOPNOTSUPP (operation not supported) if they
    are deliberately not supported, or errno.ENOSYS (function not implemented)
    if they have not yet been implemented.

    Unless otherwise documented, all paths should begin with a '/' and be
    "absolute paths", where "absolute" means relative to the root of the
    mounted filesystem. There are no references to files outside the
    filesystem.
    """
    def __init__(self, *args, **kwargs):
        """
        Creates a new TemplateFS object. Needs to call fuse.Fuse.__init__ with
        the args (just forward them along). Note that options passed to the
        filesystem through the command line are not available during the
        execution of this method.

        If parsing the command line argument fails, fsdestroy is called
        without prior calling fsinit.
        """
        logging.info("Preparing to mount file system")
        #self.file_class = File
        super(TemplateFS, self).__init__(*args, **kwargs)

        """
        After calling the superconstructor, we may optionally register
        options to be parsed from the command line arguments. To pass an
        option, use
            templatefs.py MOUNTPOINT -o xyz=VALUE -o pqr=
        which sets xyz to "VALUE" and pqr to "" (empty string).

        Not offering the equals sign is (eg. templatefs.py MOUNTPOINT -o
        enable_feature) is equivallent to not passing the option at all.

        If the same option is passed multiple times, the last one takes
        takes priority:
            templatefs.py -o xyz=a,xyz=b MOUNTPOINT -o xyz=c -o xyz=d,def=0,xyz=e

        Note that the parser will error out when a not registered option
        is passed on the command line.


        Apart from options, we can also get non-option arguments from the
        command-line:
            templatefs.py arg1 arg2 arg3 -o xyz=pqr,abc=def MOUNTPOINT
        These may be used, for example, to specify the device to be mounted.
        The mountpoint is the last non-option argument.


        You may further customize command line argument parsing setting
        the parser_class argument in __init__.
        """
        self.parser.add_option(mountopt="xyz",
                   help="description which shows up with templatefs.py -h")

    def fsinit(self):
        """
        Will be called after the command line arguments are successfully
        parsed. It doesn't have to exist or do anything, but as options to the
        filesystem are not available in __init__, fsinit is more suitable for
        the mounting logic than __init__.

        To access the command line passed options and nonoption arguments, use
        cmdline.

        The mountpoint is not stored in cmdline.
        """
        logging.info("Nonoption arguments: " + str(self.cmdline[1]))


        self.xyz = self.cmdline[0].xyz
        if self.xyz != None:
            logging.info("xyz set to '" + self.xyz + "'")
        else:
            logging.info("xyz not set")

        logging.info("Filesystem mounted")

    def fsdestroy(self):
        """
        Will be called when the file system is about to be unmounted.
        It doesn't have to exist, or do anything.
        """
        logging.info("Unmounting file system")

    def statfs(self):
        """
        Retrieves information about the mounted filesystem.
        Returns a fuse.StatVfs object containing the details.
        This is optional. If omitted, Fuse will simply report a bunch of 0s.

        The StatVfs should have the same fields as described in man 2 statfs
        (Linux Programmer's Manual), except for f_type.
        This includes the following:
            f_bsize     (optimal transfer block size)
            f_blocks    (number of blocks total)
            f_bfree     (number of free blocks)
            f_bavail    (number of free blocks available to non-root)
            f_files     (number of file nodes in system)
            f_ffree     (number of free file nodes)
            f_namemax   (max length of filenames)

        Note f_type, f_frsize, f_favail, f_fsid and f_flag are ignored.
        """
        logging.info("statfs")
        stats = fuse.StatVfs()
        # Fill it in here. All fields take on a default value of 0.
        return stats

    def getattr(self, path):
        """
        Retrieves information about a file (the "stat" of a file).
        Returns a fuse.Stat object containing details about the file or
        directory.
        Returns -errno.ENOENT if the file is not found, or another negative
        errno code if another error occurs.
        """
        logging.debug("getattr: %s" % path)
        if path == "/":
            mode = stat.S_IFDIR | 0755
            st = Stat(st_mode=mode, st_size=Stat.DIRSIZE, st_nlink=2)
        # An example of a regular file:
        #    mode = stat.S_IFREG | 0644
        #    st = Stat(st_mode=mode, st_size=14)
        # An example of a symlink (note that size is the size of the link's
        # target path string):
        #    mode = stat.S_IFLNK | 0777
        #    st = Stat(st_mode=mode, st_size=7)
        else:
            return -errno.ENOENT

        return st

    # Note: utime is deprecated in favour of utimens.
    # utimens takes precedence over utime, so having this here does nothing
    # unless you delete utimens.
    def utime(self, path, times):
        """
        Sets the access and modification times on a file.
        times: (atime, mtime) pair. Both ints, in seconds since epoch.
        Deprecated in favour of utimens.
        """
        atime, mtime = times
        logging.info("utime: %s (atime %s, mtime %s)" % (path, atime, mtime))
        return -errno.EOPNOTSUPP

    def utimens(self, path, atime, mtime):
        """
        Sets the access and modification times on a file, in nanoseconds.
        atime, mtime: Both fuse.TimeSpec objects, with 'tv_sec' and 'tv_nsec'
            attributes, which are the seconds and nanoseconds parts,
            respectively.
        """
        logging.info("utime: %s (atime %s:%s, mtime %s:%s)"
            % (path,atime.tv_sec,atime.tv_nsec,mtime.tv_sec,mtime.tv_nsec))
        return -errno.EOPNOTSUPP

    def access(self, path, flags):
        """
        Checks permissions for accessing a file or directory.
        flags: As described in man 2 access (Linux Programmer's Manual).
            Either os.F_OK (test for existence of file), or ORing of
            os.R_OK, os.W_OK, os.X_OK (test if file is readable, writable and
            executable, respectively. Must pass all tests).
        Should return 0 for "allowed", or -errno.EACCES if disallowed.
        May not always be called. For example, when opening a file, open may
        be called and access avoided.
        """
        logging.info("access: %s (flags %s)" % (path, oct(flags)))
        if path == "/":
            return 0
        else:
            return -errno.EACCES

    def readlink(self, path):
        """
        Get the target of a symlink.
        Returns a bytestring with the contents of a symlink (its target).
        May also return an int error code.
        """
        logging.info("readlink: %s" % path)
        return -errno.EOPNOTSUPP

    def mknod(self, path, mode, rdev):
        """
        Creates a non-directory file (or a device node).
        mode: Unix file mode flags for the file being created.
        rdev: Special properties for creation of character or block special
            devices (I've never gotten this to work).
            Always 0 for regular files or FIFO buffers.
        """
        # Note: mode & 0770000 gives you the non-permission bits.
        # Common ones:
        # S_IFREG:  0100000 (A regular file)
        # S_IFIFO:  010000  (A fifo buffer, created with mkfifo)

        # Potential ones (I have never seen them):
        # Note that these could be made by copying special devices or sockets
        # or using mknod, but I've never gotten FUSE to pass such a request
        # along.
        # S_IFCHR:  020000  (A character special device, created with mknod)
        # S_IFBLK:  060000  (A block special device, created with mknod)
        # S_IFSOCK: 0140000 (A socket, created with mkfifo)

        # Also note: You can use self.GetContext() to get a dictionary
        #   {'uid': ?, 'gid': ?}, which tells you the uid/gid of the user
        #   executing the current syscall. This should be handy when creating
        #   new files and directories, because they should be owned by this
        #   user/group.
        logging.info("mknod: %s (mode %s, rdev %s)" % (path, oct(mode), rdev))
        return -errno.EOPNOTSUPP

    def mkdir(self, path, mode):
        """
        Creates a directory.
        mode: Unix file mode flags for the directory being created.
        """
        # Note: mode & 0770000 gives you the non-permission bits.
        # Should be S_IDIR (040000); I guess you can assume this.
        # Also see note about self.GetContext() in mknod.
        logging.info("mkdir: %s (mode %s)" % (path, oct(mode)))
        return -errno.EOPNOTSUPP

    def unlink(self, path):
        """Deletes a file."""
        logging.info("unlink: %s" % path)
        return -errno.EOPNOTSUPP

    def rmdir(self, path):
        """Deletes a directory."""
        logging.info("rmdir: %s" % path)
        return -errno.EOPNOTSUPP

    def symlink(self, target, name):
        """
        Creates a symbolic link from path to target.

        The 'name' is a regular path like any other method (absolute, but
        relative to the filesystem root).
        The 'target' is special - it works just like any symlink target. It
        may be absolute, in which case it is absolute on the user's system,
        NOT the mounted filesystem, or it may be relative. It should be
        treated as an opaque string - the filesystem implementation should not
        ever need to follow it (that is handled by the OS).

        Hence, if the operating system creates a link FROM this system TO
        another system, it will call this method with a target pointing
        outside the filesystem.
        If the operating system creates a link FROM some other system TO this
        system, it will not touch this system at all (symlinks do not depend
        on the target system unless followed).
        """
        logging.info("symlink: target %s, name: %s" % (target, name))
        return -errno.EOPNOTSUPP

    def link(self, target, name):
        """
        Creates a hard link from name to target. Note that both paths are
        relative to the mounted file system. Hard-links across systems are not
        supported.
        """
        logging.info("link: target %s, name: %s" % (target, name))
        return -errno.EOPNOTSUPP

    def rename(self, old, new):
        """
        Moves a file from old to new. (old and new are both full paths, and
        may not be in the same directory).
        
        Note that both paths are relative to the mounted file system.
        If the operating system needs to move files across systems, it will
        manually copy and delete the file, and this method will not be called.
        """
        logging.info("rename: target %s, name: %s" % (old, new))
        return -errno.EOPNOTSUPP

    def chmod(self, path, mode):
        """Changes the mode of a file or directory."""
        logging.info("chmod: %s (mode %s)" % (path, oct(mode)))
        return -errno.EOPNOTSUPP

    def chown(self, path, uid, gid):
        """Changes the owner of a file or directory."""
        logging.info("chown: %s (uid %s, gid %s)" % (path, uid, gid))
        return -errno.EOPNOTSUPP

    def truncate(self, path, size):
        """
        Shrink or expand a file to a given size.
        If 'size' is smaller than the existing file size, truncate it from the
        end.
        If 'size' if larger than the existing file size, extend it with null
        bytes.
        """
        logging.info("truncate: %s (size %s)" % (path, size))
        return -errno.EOPNOTSUPP

    ### DIRECTORY OPERATION METHODS ###
    # Methods in this section are operations for opening directories and
    # working on open directories.
    # "opendir" is the method for opening directories. It *may* return an
    # arbitrary Python object (not None or int), which is used as a dir
    # handle by the methods for working on directories.
    # All the other methods (readdir, fsyncdir, releasedir) are methods for
    # working on directories. They should all be prepared to accept an
    # optional dir-handle argument, which is whatever object "opendir"
    # returned.

    def opendir(self, path):
        """
        Checks permissions for listing a directory.
        This should check the 'r' (read) permission on the directory.

        On success, *may* return an arbitrary Python object, which will be
        used as the "fh" argument to all the directory operation methods on
        the directory. Or, may just return None on success.
        On failure, should return a negative errno code.
        Should return -errno.EACCES if disallowed.
        """
        logging.info("opendir: %s" % path)
        if path == "/":
            return 0
        else:
            return -errno.EACCES

    def releasedir(self, path, dh=None):
        """
        Closes an open directory. Allows filesystem to clean up.
        """
        logging.info("releasedir: %s (dh %s)" % (path, dh))

    def fsyncdir(self, path, datasync, dh=None):
        """
        Synchronises an open directory.
        datasync: If True, only flush user data, not metadata.
        """
        logging.info("fsyncdir: %s (datasync %s, dh %s)"
            % (path, datasync, dh))

    def readdir(self, path, offset, dh=None):
        """
        Generator function. Produces a directory listing.
        Yields individual fuse.Direntry objects, one per file in the
        directory. Should always yield at least "." and "..".
        Should yield nothing if the file is not a directory or does not exist.
        (Does not need to raise an error).

        offset: I don't know what this does, but I think it allows the OS to
        request starting the listing partway through (which I clearly don't
        yet support). Seems to always be 0 anyway.
        """
        logging.info("readdir: %s (offset %s, dh %s)" % (path, offset, dh))
        if path == "/":
            yield fuse.Direntry(".")
            yield fuse.Direntry("..")

    ### FILE OPERATION METHODS ###
    # Methods in this section are operations for opening files and working on
    # open files.
    # "open" and "create" are methods for opening files. They *may* return an
    # arbitrary Python object (not None or int), which is used as a file
    # handle by the methods for working on files.
    # All the other methods (fgetattr, release, read, write, fsync, flush,
    # ftruncate and lock) are methods for working on files. They should all be
    # prepared to accept an optional file-handle argument, which is whatever
    # object "open" or "create" returned.

    def open(self, path, flags):
        """
        Open a file for reading/writing, and check permissions.
        flags: As described in man 2 open (Linux Programmer's Manual).
            ORing of several access flags, including one of os.O_RDONLY,
            os.O_WRONLY or os.O_RDWR. All other flags are in os as well.

        On success, *may* return an arbitrary Python object, which will be
        used as the "fh" argument to all the file operation methods on the
        file. Or, may just return None on success.
        On failure, should return a negative errno code.
        Should return -errno.EACCES if disallowed.
        """
        logging.info("open: %s (flags %s)" % (path, oct(flags)))
        return -errno.EOPNOTSUPP

    def create(self, path, mode, rdev):
        """
        Creates a file and opens it for writing.
        Will be called in favour of mknod+open, but it's optional (OS will
        fall back on that sequence).
        mode: Unix file mode flags for the file being created.
        rdev: Special properties for creation of character or block special
            devices (I've never gotten this to work).
            Always 0 for regular files or FIFO buffers.
        See "open" for return value.
        """
        logging.info("create: %s (mode %s, rdev %s)" % (path,oct(mode),rdev))
        return -errno.EOPNOTSUPP

    def fgetattr(self, path, fh=None):
        """
        Retrieves information about a file (the "stat" of a file).
        Same as Fuse.getattr, but may be given a file handle to an open file,
        so it can use that instead of having to look up the path.
        """
        logging.debug("fgetattr: %s (fh %s)" % (path, fh))
        # We could use fh for a more efficient lookup. Here we just call the
        # non-file-handle version, getattr.
        return self.getattr(path)

    def release(self, path, flags, fh=None):
        """
        Closes an open file. Allows filesystem to clean up.
        flags: The same flags the file was opened with (see open).
        """
        logging.info("release: %s (flags %s, fh %s)" % (path, oct(flags), fh))

    def fsync(self, path, datasync, fh=None):
        """
        Synchronises an open file.
        datasync: If True, only flush user data, not metadata.
        """
        logging.info("fsync: %s (datasync %s, fh %s)" % (path, datasync, fh))

    def flush(self, path, fh=None):
        """
        Flush cached data to the file system.
        This is NOT an fsync (I think the difference is fsync goes both ways,
        while flush is just one-way).
        """
        logging.info("flush: %s (fh %s)" % (path, fh))

    def read(self, path, size, offset, fh=None):
        """
        Get all or part of the contents of a file.
        size: Size in bytes to read.
        offset: Offset in bytes from the start of the file to read from.
        Does not need to check access rights (operating system will always
        call access or open first).
        Returns a byte string with the contents of the file, with a length no
        greater than 'size'. May also return an int error code.

        If the length of the returned string is 0, it indicates the end of the
        file, and the OS will not request any more. If the length is nonzero,
        the OS may request more bytes later.
        To signal that it is NOT the end of file, but no bytes are presently
        available (and it is a non-blocking read), return -errno.EAGAIN.
        If it is a blocking read, just block until ready.
        """
        logging.info("read: %s (size %s, offset %s, fh %s)"
            % (path, size, offset, fh))
        return -errno.EOPNOTSUPP

    def write(self, path, buf, offset, fh=None):
        """
        Write over part of a file.
        buf: Byte string containing the text to write.
        offset: Offset in bytes from the start of the file to write to.
        Does not need to check access rights (operating system will always
        call access or open first).
        Should only overwrite the part of the file from offset to
        offset+len(buf).

        Must return an int: the number of bytes successfully written (should
        be equal to len(buf) unless an error occured). May also be a negative
        int, which is an errno code.
        """
        logging.info("write: %s (offset %s, fh %s)" % (path, offset, fh))
        logging.debug("  buf: %r" % buf)
        return -errno.EOPNOTSUPP

    def ftruncate(self, path, size, fh=None):
        """
        Shrink or expand a file to a given size.
        Same as Fuse.truncate, but may be given a file handle to an open file,
        so it can use that instead of having to look up the path.
        """
        logging.info("ftruncate: %s (size %s, fh %s)" % (path, size, fh))
        return -errno.EOPNOTSUPP

class File(object):
    """
    An open File handle. Like Fuse objects, supports a number of
    specially-named methods which are called when the filesystem needs to
    access the file in question.

    Note: Implementing this class is an *alternative* to implementing the
    above "file operation methods" in Fuse itself. If this class is
    implemented, the following line should appear in Fuse.__init__:

    self.file_class = File

    Also, all of the "file operation methods" should be removed from Fuse, as
    they take priority over the File class.

    The File class is simply a more object oriented way to implement the same
    methods.
    """
    def __init__(self, path, flags, mode=None):
        """
        File-class version of "open" and "create" combined.
        Opens a file (possibly creating it, if mode is supplied).

        Note that you have no way to see the Fuse object which created it.
        The documentation suggests a workaround (search for
        "wrapped_file_class"). Note that this class is supposed to go inside
        Fuse.__init__.
        http://apps.sourceforge.net/mediawiki/fuse/index.php
            ?title=FUSE_Python_Reference
        This alone might be a reason to avoid using the File class, and
        instead go with the more direct approach.
        """
        logging.info("File.__init__: %s (flags %s, mode %s)"
            % (path, oct(flags), None if mode is None else oct(mode)))
        self.path = path

    def __repr__(self):
        return "<File %r>" % self.path

    def fgetattr(self):
        """
        File-class version of "getattr".
        Retrieves information about a file (the "stat" of a file).
        """
        logging.info("%r.fgetattr" % self)
        return -errno.EOPNOTSUPP

    def release(self, flags):
        """
        File-class version of "release".
        Closes an open file. Allows filesystem to clean up.
        """
        logging.info("%r.release (flags %s)" % (self, oct(flags)))

    def fsync(self, datasync):
        """
        File-class version of "fsync".
        Synchronises an open file.
        """
        logging.info("%r.fsync (datasync %s)" % (self, datasync))

    def flush(self):
        """
        File-class version of "flush".
        Flush cached data to the file system.
        """
        logging.info("%r.flush" % self)

    def read(self, size, offset):
        """
        File-class version of "read".
        Get all or part of the contents of a file.
        """
        logging.info("%r.read (size %s, offset %s)" % (self, size, offset))
        return -errno.EOPNOTSUPP

    def write(self, buf, offset):
        """
        File-class version of "write".
        Write over part of a file.
        """
        logging.info("%r.write (offset %s)" % (self, offset))
        logging.debug("  buf: %r" % buf)
        return -errno.EOPNOTSUPP

    def ftruncate(self, size):
        """
        File-class version of "ftruncate".
        Shrink or expand a file to a given size.
        """
        logging.info("%r.ftruncate (size %s)" % (self, size))
        return -errno.EOPNOTSUPP
