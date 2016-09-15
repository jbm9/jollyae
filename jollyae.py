#!/usr/bin/env python

# Schleps files from the upload/ directory up to a remote fileserver,
# then moves them to the archive/ directory so the archiver can do its
# thing.

import os
import os.path
import sys

import time
from watchdog.observers import Observer
import watchdog.events

import random

import boto
from boto.s3.key import Key

from optparse import OptionParser

class UploaderEventHandler(watchdog.events.FileSystemEventHandler):
    def __init__(self, options):
        problems = self._validate_options(options)
        if problems:
            print "Errors in the specified config:"
            print "\n".join(problems)
            sys.exit(1)


        self.src = options.src
        self.interim = options.interim
        self.dest = options.dest
        self.fail = options.fail

        
        self.no_upload = options.no_upload
        self.random_no_upload_fail = options.random_no_upload_fail
        self.bucket = options.bucket
        self.acl = options.acl

        self.remove = options.remove
        self.remove_failed = options.remove_failed

        self.verbose = options.verbose

        self._log("Starting up...")
                
        if not self.no_upload:
            self._log("Connecting to S3")
            self.c = boto.connect_s3()
            
            self._log("Getting the bucket: %s" % self.bucket)
            self.b = self.c.get_bucket(self.bucket)

            # Workaround needed for non-us-east-1 buckets sometimes
            bucket_location = self.b.get_location()
            if bucket_location:
                self._log("Reconnecting to s3 for %s" % bucket_location)
                self.c = boto.s3.connect_to_region(bucket_location)
                
                self._log("Getting the bucket %s for location %s" % (self.bucket, bucket_location))
                self.b = self.c.get_bucket(self.bucket)


    def _validate_options(self, options):
        problems = []
        if not options.src:
            problems.append("Need a src directory")

        if options.dest and options.remove:
            problems.append("Specified both a destination and deletion. If you want to nuke files, please use --interim")
            
        if not options.dest and not (options.interim and options.remove):
            problems.append("Need either a final destination or a tempdir-and-remove")

        if options.fail and options.remove_failed:
            problems.append("Specified both remove-failed and a filed directory")
            
        if options.src and not os.path.isdir(options.src):
            problems.append("Source path is not a directory")
            
        if options.interim and not os.path.isdir(options.interim):
            problems.append("Interim path is not a directory")
            
        if options.dest and not os.path.isdir(options.dest):
            problems.append("Destination path is not a dir")

        if options.fail and not os.path.isdir(options.fail):
            problems.append("Fail path is not a dir")

            
        if not options.no_upload and not options.bucket:
            problems.append("Need a bucket to save to")

        if options.interim == options.dest:
            problems.append("interimdir is the same as destination")

        if options.interim == options.src:
            problems.append("interimdir is the same as source")
            
        if options.dest == options.src:
            problems.append("Destination is the same as source")

        # NB: src == fail is a valid use case
            
        if options.no_upload and 0.0 == options.random_no_upload_fail and options.remove:
            problems.append("No-upload and remove are set: please use rm(1) directly.")

        if not options.no_upload:
            if None == os.getenv("AWS_ACCESS_KEY_ID"):
                problems.append("Need AWS_ACCESS_KEY_ID set in environment")
            
            if None == os.getenv("AWS_SECRET_ACCESS_KEY"):
                problems.append("Need AWS_SECRET_ACCESS_KEY set in environment")

        return problems

    def _log(self, s):
        if self.verbose:
            print s

    def _upload(self, filename, p):
        self._log("Uploading s3://%s/%s from %s" % (self.bucket, filename, p))
        if self.no_upload:
            if random.uniform(0.0, 1.0) < self.random_no_upload_fail:
                self._log("No upload: Random failure")
                raise Exception("No upload: beep boom: Random S3 failure")
            else:
                self._log("No upload: beep boop pretend to upload to S3, success!")
        else:
            k = Key(self.b)
            k.key = filename
            k.set_contents_from_filename(p)
            if self.acl:
                self._log("Setting ACL: %s" % self.acl)
                k.set_acl(self.acl)
        self._log("Upload finished: %s" % filename)

    def _rename(self, p1, p2):
        self._log("  rename(%s, %s)" % (p1,p2))
        os.rename(p1,p2)

    def _remove(self, p):
        self._log("  removing %s" % p)
        os.remove(p)
                
    def _handle(self, p):        
        filename = os.path.basename(p)
        
        self._log("handling %s: %s" % (p, filename))
        
        interim_dir = self.interim or self.dest
        interim_path = os.path.join(interim_dir, filename)

        final_path = interim_path
        if self.dest:
            final_path = os.path.join(self.dest, filename)
        
        try:
            self._rename(p, interim_path)
        except OSError:
            self._log("Couldn't snag %s" % filename)
            # Somebody else got there first
            return
        except:
            raise

        try:
            self._upload(filename, interim_path)
        except Exception, e:
            self._log("FAIL: filename=%s, exception=%s" % (filename, str(e)))
            
            if self.fail:
                fail_path = os.path.join(self.fail, filename)
                self._rename(interim_path, fail_path)
            elif self.remove_failed:
                try:
                    self._remove(interim_path)
                except OSError:
                    pass
            else:
                raise e
            return

        if self.remove:
            self._remove(interim_path)
        elif final_path != interim_path:
            self._rename(interim_path, final_path)


    def dispatch(self, evt):
        if evt.event_type != "created":
            return
        print "Got new file: %s" % evt.src_path
        self._handle(evt.src_path)
        print "Handled: %s" % evt.src_path

if __name__ == "__main__":
    parser = OptionParser(usage="%prog: [options]")

    parser.add_option("-b", "--bucket", help="Destination S3 bucket")
    parser.add_option("-a", "--acl", help="ACL to set on file after upload")
    
    parser.add_option("-n", "--no-upload", help="Fake out the upload", default=False, action="store_true")
    parser.add_option("--random-no-upload-fail", help="For no-upload, fail randomly about this fraction of the time (default: 0.0, 1.0 is 100%)", type=float, default=0.0)
    parser.add_option("-s", "--src", help="Source directory")
    parser.add_option("-d", "--dest", help="Destination directory")
    parser.add_option("-i", "--interim", help="Interim directory (default: destination)")
    parser.add_option("-f", "--fail", help="Path to move failed jobs to (default: destination)")
    parser.add_option("-r", "--remove", help="Remove when done", default=False, action="store_true")
    parser.add_option("-R", "--remove-failed", help="Remove failed items", default=False, action="store_true")

    parser.add_option("-v", "--verbose", help="Be verbose", default=False, action="store_true")


    (options, args) = parser.parse_args()

    observer = Observer()
    handler = UploaderEventHandler(options)
    observer.schedule(handler, options.src, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
