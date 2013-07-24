#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import locale
import tempfile
import logging
from ConfigParser import SafeConfigParser
from dropbox import client
# import flickr_api
# from oauth import oauth
# import uniout
import requests
import md5
import json

logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

CONF_FILE = 'cacasync.conf'


class CaCaSync(object):

    def __init__(self, dropbox, flickr=None, gplus=None):
        self.dropbox = dropbox
        self.flickr = flickr
        self.gplus = gplus

    def dropbox_sync_flickr(self, dropbox_folder=''):
        file_set = self.dropbox.download_folder(dropbox_folder)
        print(file_set)

    def dropbox_diff_flickr(self):
        diff_set = set()
        folder_queue = []
        dropbox_file_set = self.dropbox.ls()
        flickr_file_set, flickr_index_dict = self.flickr.ls()
        # diff_list =


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

    def ls(self, path=''):
        resp = self.api_client.metadata(
            self.current_path + os.sep + path
        )
        file_set = set()
        if 'contents' in resp:
            for f in resp['contents']:
                path_tokens = f['path'].split(os.sep)
                name = os.sep.join(path_tokens[1:])
                encoding = locale.getdefaultlocale()[1]
                file_set.add(('%s'.format(name)).encode(encoding))
        return file_set

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
        file_set = self.ls(from_path)
        to_path = self.tmp_dir + os.sep + from_path
        os.makedirs(to_path)
        for f in file_set:
            self.download_file(from_path + os.sep + f, to_path + os.sep + f)
        return file_set


class Flickr(object):

    def __init__(self, api_key, api_secret, app_token, app_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.app_token = app_token
        self.app_secret = app_secret
        self.rest_url = 'http://flickr.com/services/rest/'

        # flickr_api.set_keys(api_key, api_secret)
        # self.api_client = flickr_api.auth.AuthHandler(callback=None)
        # self.api_client.access_token = oauth.OAuthToken(
        #     app_token,
        #     app_secret
        # )
        # flickr_api.set_auth_handler(self.api_client)
        # self.user = flickr_api.test.login()
        self.photosets_index_dict = None
        self.photoset_titles = None

    def _get_request_args(self, method, **kwargs):
        args = [
            ('api_key', self.api_key),
            ('auth_token', self.app_token),
            ('format', 'json'),
            ('method', method),
            ('nojsoncallback', '1'),
        ]
        if kwargs:
            print(kwargs)
            for key, value in kwargs.iteritems():
                args.append((key, value))
        args.sort(key=lambda tup: tup[0])
        api_sig = self._get_api_sig(args)
        args.append(api_sig)
        return args

    def _get_api_sig(self, args):
        tmp_sig = self.api_secret
        for i in args:
            tmp_sig = tmp_sig + i[0] + i[1]
        api_sig = md5.new(tmp_sig).hexdigest()
        return ('api_sig', api_sig)

    def get_photosets_info(self):
        args = self._get_request_args('flickr.photosets.getList')
        resp = requests.post(self.rest_url, params=args)
        logger.debug(resp.text.encode('utf-8'))
        resp_json = json.loads(resp.text.encode('utf-8'))
        photosets = resp_json['photosets']['photoset']
        # photosets = self.user.getPhotosets()
        index_dict = {}
        titles = set()
        for photoset in photosets:
            title = photoset['title']['_content']
            index_dict[title] = photoset['id']
            titles.add(title)
        self.photoset_titles = titles
        self.photosets_index_dict = index_dict
        return titles, index_dict

    def get_photos(self, photoset_name):
        photoset_id = self.photosets_index_dict[photoset_name]
        args = self._get_request_args(
            'flickr.photosets.getPhotos',
            photoset_id=photoset_id
        )
        resp = requests.get(self.rest_url, params=args)
        logger.debug(resp.text.encode('utf-8'))
        resp_json = json.loads(resp.text.encode('utf-8'))
        photos = resp_json['photos']
        index_dict = {}
        titles = set()
        for photo in photos:
            index_dict[photo['title']] = photo['id']
            titles.add(photo['title'])
        return titles, index_dict
        # photos = photoset.getPhotos()
        # print(photos)


def main():
    parser = SafeConfigParser()
    parser.read(CONF_FILE)

    # dropbox_api_key = parser.get('dropbox', 'APP_KEY')
    # dropbox_api_secret = parser.get('dropbox', 'APP_SECRET')

    # dropbox_app_token = parser.get('dropbox', 'APP_TOKEN')
    # dropbox_current_path = parser.get('dropbox', 'CURRENT_PATH')

    # dropbox = Dropbox(
    #     dropbox_api_key,
    #     dropbox_api_secret,
    #     dropbox_app_token,
    #     dropbox_current_path
    # )

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
    flickr.get_photosets_info()
    flickr.get_photos('box')

    # cacasync = CaCaSync(dropbox, flickr)
    # cacasync.dropbox_sync_flickr('test')


if __name__ == '__main__':
    main()
