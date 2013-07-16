#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import locale
from ConfigParser import SafeConfigParser
from dropbox import client


class CaCaSync(object):
    CONF_FILE = 'cacasync.conf'

    def __init__(self):
        parser = SafeConfigParser()
        parser.read(self.CONF_FILE)

        self.dropbox_key = parser.get('dropbox', 'APP_KEY')
        self.dropbox_secret = parser.get('dropbox', 'APP_SECRET')
        self.dropbox_current_path = ''
        self.dropbox_api_client = None
        try:
            token = parser.get('dropbox', 'APP_TOKEN')
            self.dropbox_api_client = client.DropboxClient(token)
            print "[loaded access token]"
        except IOError:
            pass  # don't worry if it's not there

    def ls(self):
        resp = self.dropbox_api_client.metadata('')

        if 'contents' in resp:
            for f in resp['contents']:
                name = os.path.basename(f['path'])
                encoding = locale.getdefaultlocale()[1]
                print(('%s' % name).encode(encoding))

    def get(self, from_path, to_path):
        """
        Copy file from Dropbox to local file and print out the metadata.

        Examples:
        Dropbox> get file.txt ~/dropbox-file.txt
        """
        to_file = open(os.path.expanduser(to_path), "wb")

        f, metadata = self.dropbox_api_client.get_file_and_metadata(
            self.dropbox_current_path + "/" + from_path
        )
        print 'Metadata:', metadata
        to_file.write(f.read())


def main():
    cacasync = CaCaSync()
    cacasync.ls()

if __name__ == '__main__':
    main()
