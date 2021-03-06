#!/usr/bin/env python3

import logging
import sys
sys.path+=['..']
from RTEAgent import *
import threading

from collections import defaultdict
from errno import ENOENT,EACCES
from stat import S_IFDIR, S_IFLNK, S_IFREG
from sys import argv, exit
from time import time

from fuse import FUSE, Operations, LoggingMixIn, FuseOSError

if not hasattr(__builtins__, 'bytes'):
    bytes = str

class RTEAThread( threading.Thread ):
    def __init__( self, rteFS, rteAgent,filename, contents ):
        threading.Thread.__init__(self)
        self.rteFS = rteFS
        self.rteAgent = rteAgent
        self.filename = filename
        self.contents = contents
    def run( self ):
        logging.debug("Compile thread compiling, from change in file "+self.filename)
        self.rteAgent.input( self.filename, self.contents )
        self.rteFS.files['/input']['st_mode'] = (S_IFDIR | 0o777)
        logging.debug("Compile thread finished")
        
class RTEFS(LoggingMixIn, Operations):
    'FS for control of the Real-Time Editing agent, drawing from the fusepy Example memory filesystem.'

    def __init__(self, agent):
        self.files = {}
        self.data = defaultdict(bytes)
        self.fd = 0
        now = time()
        self.files['/'] = dict(st_mode=(S_IFDIR | 0o777), st_ctime=now,
                               st_mtime=now, st_atime=now, st_nlink=2)
        self.files['/input'] = dict(st_mode=(S_IFDIR | 0o777), st_ctime=now,
                               st_mtime=now, st_atime=now, st_nlink=2)
        self.agent = agent
        
    def chmod(self, path, mode):
        self.files[path]['st_mode'] &= 0o770000
        self.files[path]['st_mode'] |= mode
        return 0

    def chown(self, path, uid, gid):
        self.files[path]['st_uid'] = uid
        self.files[path]['st_gid'] = gid

    def create(self, path, mode):
        self.files[path] = dict(st_mode=(S_IFREG | mode), st_nlink=1,
                                st_size=0, st_ctime=time(), st_mtime=time(),
                                st_atime=time())

        self.fd += 1
        return self.fd

    def getattr(self, path, fh=None):
        if path[0:7] == "/input/":
            st = os.lstat(agent.cwd + path[6:])
            self.files[path] = dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                                                            'st_gid', 'st_mode', 'st_mtime', 'st_nlink',
                                                            'st_size', 'st_uid'))
            return self.files[path]
        if path not in self.files:
            raise OSError(ENOENT)

        return self.files[path]

    def getxattr(self, path, name, position=0):
        attrs = self.files[path].get('attrs', {})

        try:
            return attrs[name]
        except KeyError:
            return ''       # Should return ENOATTR

    def listxattr(self, path):
        attrs = self.files[path].get('attrs', {})
        return attrs.keys()

    def mkdir(self, path, mode):
        self.files[path] = dict(st_mode=(S_IFDIR | mode), st_nlink=2,
                                st_size=0, st_ctime=time(), st_mtime=time(),
                                st_atime=time())

        self.files['/']['st_nlink'] += 1

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def read(self, path, size, offset, fh):
        return self.data[path][offset:offset + size]

    def readdir(self, path, fh):
        return ['.', '..'] + [x[1:] for x in self.files if x != '/']

    def readlink(self, path):
        return self.data[path]

    def removexattr(self, path, name):
        attrs = self.files[path].get('attrs', {})

        try:
            del attrs[name]
        except KeyError:
            pass        # Should return ENOATTR

    def rename(self, old, new):
        self.files[new] = self.files.pop(old)

    def rmdir(self, path):
        self.files.pop(path)
        self.files['/']['st_nlink'] -= 1

    def statfs(self, path):
        return dict(f_bsize=512, f_blocks=4096, f_bavail=2048)

    def symlink(self, target, source):
        self.files[target] = dict(st_mode=(S_IFLNK | 0o777), st_nlink=1,
                                  st_size=len(source))

        self.data[target] = source

    def truncate(self, path, length, fh=None):
        self.data[path] = self.data[path][:length]
        self.files[path]['st_size'] = length

    def unlink(self, path):
        self.files.pop(path)

    def utimens(self, path, times=None):
        now = time()
        atime, mtime = times if times else (now, now)
        self.files[path]['st_atime'] = atime
        self.files[path]['st_mtime'] = mtime

    def write(self, path, data, offset, fh):
        self.data[path] = self.data[path][:offset] + data
        self.files[path]['st_size'] = len(self.data[path])
        return len(data)

    def release( self, path, fh ):
        #logging.debug("Releasing path : "+path)
        #logging.debug("Data at the end of interaction is :"+self.data[path])
        if path[0:7] == '/input/':
            #logging.debug("input file written, let's launch the whole shebang")
            #Input file written
            #We remove writing rights to /input/ to prevent further editing
            self.files['/input']['st_mode'] = (S_IFDIR | 0000)
            #We launch the thread that will give them back
            RTEAThread( self, self.agent,path[7:],self.data[path] ).start()
            #TODO: We should check if a previous compilation is still running
            #logging.debug("thread started, returning")
        #Give back control to user
        return 0

    def access( self, path, mode ):
        logging.debug("Calling access on "+path)
        if path[0:6] == '/input':
            logging.debug("Checking wether /input can be accessed")
            if self.files['/input']['st_mode'] == (S_IFDIR | 0000):
                logging.debug("Nope")
                raise FuseOSError(EACCES)
            logging.debug("Yep")
        return 0
        


    
if __name__ == '__main__':
    if len(argv) != 2:
        print('usage: %s <mountpoint>' % argv[0])
        exit(1)

    logging.getLogger().setLevel(logging.INFO) #Or DEBUG ...
    logging.debug("Launching the agent")
    agent = RTEAgent()
    fuse = FUSE(RTEFS( agent ), argv[1], foreground=True,auto_xattr=True)
    

