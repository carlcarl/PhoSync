#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import locale
import tempfile
from ConfigParser import SafeConfigParser
from dropbox import client

CONF_FILE = 'cacasync.conf'


class CaCaSync(object):
    def __init__():
        pass


class Dropbox(object):

    def __init__(
        self, dropbox_key, dropbox_secret, dropbox_token, dropbox_current_path
    ):
        self.dropbox_key = dropbox_key
        self.dropbox_secret = dropbox_secret
        self.dropbox_token = dropbox_token
        self.dropbox_current_path = dropbox_current_path

        self.dropbox_api_client = client.DropboxClient(dropbox_token)
        tmp_dir = tempfile.gettempdir() + os.sep + 'cacasync'
        if os.path.exists(tmp_dir):
            if not os.path.isdir(tmp_dir):
                sys.exit(1)
        else:
            os.mkdir(tmp_dir)
        print(tmp_dir)
        self.tmp_dir = tmp_dir
        print "[loaded access token]"

    def ls(self, path):
        resp = self.dropbox_api_client.metadata(
            self.dropbox_current_path + os.sep + path
        )
        file_list = []
        if 'contents' in resp:
            for f in resp['contents']:
                name = os.path.basename(f['path'])
                encoding = locale.getdefaultlocale()[1]
                file_list.append(('%s' % name).encode(encoding))
        return file_list

    def get(self, from_path, to_path):
        """
        Copy file from Dropbox to local file and print out the metadata.

        Examples:
        Dropbox> get file.txt ~/dropbox-file.txt
        """
        to_file = open(os.path.expanduser(to_path), 'wb')

        f, metadata = self.dropbox_api_client.get_file_and_metadata(
            self.dropbox_current_path + os.sep + from_path
        )
        # print 'Metadata:', metadata
        to_file.write(f.read())

    def get_folder(self, from_path):
        file_list = self.ls(from_path)
        to_path = self.tmp_dir + os.sep + from_path
        os.makedirs(to_path)
        for f in file_list:
            self.get(from_path + os.sep + f, to_path + os.sep + f)


def main():
    parser = SafeConfigParser()
    parser.read(CONF_FILE)

    dropbox_key = parser.get('dropbox', 'APP_KEY')
    dropbox_secret = parser.get('dropbox', 'APP_SECRET')

    dropbox_token = parser.get('dropbox', 'APP_TOKEN')
    dropbox_current_path = parser.get('dropbox', 'CURRENT_PATH')

    dropbox = Dropbox(
        dropbox_key,
        dropbox_secret,
        dropbox_token,
        dropbox_current_path
    )
    dropbox.get_folder('test')

if __name__ == '__main__':
    main()
