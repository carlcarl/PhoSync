#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import locale
import tempfile
import logging
from ConfigParser import SafeConfigParser
from dropbox import client
import flickr_api
from oauth import oauth

logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

CONF_FILE = 'cacasync.conf'


class CaCaSync(object):

    def __init__(self, dropbox, flickr=None, gplus=None):
        self.dropbox = dropbox
        self.flickr = flickr
        self.gplus = gplus

    def dropbox_sync_flickr(self, dropbox_folder=''):
        file_list = self.dropbox.download_folder(dropbox_folder)
        print(file_list)


class Dropbox(object):

    def __init__(
        self, api_key, api_secret, app_token, current_path
    ):
        self.api_token = api_key
        self.api_secret = api_secret
        self.app_token = app_token
        self.current_path = current_path

        self.api_client = client.DropboxClient(app_token)

        tmp_dir = tempfile.gettempdir() + os.sep + 'cacasync'
        self._make_tmp_dir(tmp_dir)
        tmp_dir = tmp_dir + os.sep + app_token
        self._make_tmp_dir(tmp_dir)
        self.tmp_dir = tmp_dir

    def _make_tmp_dir(self, tmp_dir):
        if os.path.exists(tmp_dir):
            if not os.path.isdir(tmp_dir):
                logger.error('{path} is not a directory'.format(path=tmp_dir))
                sys.exit(1)
        else:
            os.mkdir(tmp_dir)

    def ls(self, path):
        resp = self.api_client.metadata(
            self.current_path + os.sep + path
        )
        file_list = []
        if 'contents' in resp:
            for f in resp['contents']:
                name = os.path.basename(f['path'])
                encoding = locale.getdefaultlocale()[1]
                file_list.append(('%s' % name).encode(encoding))
        return file_list

    def download_file(self, from_path, to_path):
        """
        Copy file from Dropbox to local file and print out the metadata.

        Examples:
        Dropbox> get file.txt ~/dropbox-file.txt
        """
        to_file = open(os.path.expanduser(to_path), 'wb')

        f, metadata = self.api_client.get_file_and_metadata(
            self.current_path + os.sep + from_path
        )
        # print 'Metadata:', metadata
        to_file.write(f.read())

    def download_folder(self, from_path):
        file_list = self.ls(from_path)
        to_path = self.tmp_dir + os.sep + from_path
        os.makedirs(to_path)
        for f in file_list:
            self.get(from_path + os.sep + f, to_path + os.sep + f)
        return file_list


class Flickr(object):

    def __init__(self, api_key, api_secret, app_token, app_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.app_token = app_token
        self.app_secret = app_secret

        flickr_api.set_keys(api_key, api_secret)
        self.api_client = flickr_api.auth.AuthHandler(callback=None)
        self.api_client.access_token = oauth.OAuthToken(
            app_token,
            app_secret
        )
        flickr_api.set_auth_handler(self.api_client)
        self.user = flickr_api.test.login()


def main():
    parser = SafeConfigParser()
    parser.read(CONF_FILE)

    dropbox_api_key = parser.get('dropbox', 'APP_KEY')
    dropbox_api_secret = parser.get('dropbox', 'APP_SECRET')

    dropbox_app_token = parser.get('dropbox', 'APP_TOKEN')
    dropbox_current_path = parser.get('dropbox', 'CURRENT_PATH')

    dropbox = Dropbox(
        dropbox_api_key,
        dropbox_api_secret,
        dropbox_app_token,
        dropbox_current_path
    )

    flickr_api_key = parser.get('flickr', 'API_KEY')
    flickr_api_secret = parser.get('flickr', 'API_SECRET')

    flickr_app_token = parser.get('flickr', 'APP_TOKEN')
    flickr_app_secret = parser.get('flickr', 'APP_SECRET')

    flickr = Flickr(
        flickr_api_key,
        flickr_api_secret,
        flickr_app_token,
        flickr_app_secret
    )

    cacasync = CaCaSync(dropbox, flickr)
    cacasync.dropbox_sync_flickr('test')


if __name__ == '__main__':
    main()
