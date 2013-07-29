#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import shutil
import tempfile
import logging
from ConfigParser import SafeConfigParser
from dropbox import client
import uniout
assert uniout
import requests
import md5
import json
from xml.dom import minidom

logger = logging.getLogger(__name__)
CONF_FILE = 'cacasync.conf'
TMP_DIR = ''


class CaCaSync(object):

    def __init__(self, dropbox, flickr=None, gplus=None):
        self.dropbox = dropbox
        self.flickr = flickr
        self.gplus = gplus

    def sync_flickr(self):
        dropbox_list, dropbox_meta = self.dropbox.ls()
        flickr_list, flickr_meta = self.flickr.get_photosets_info()
        upload_set, base_set = self.diff_flickr(
            dropbox_list,
            flickr_list
        )
        for folder in upload_set:
            self._sync_flickr_root(folder)
        for folder in base_set:
            sub_dropbox_list, sub_dropbox_meta = self.dropbox.ls(folder)
            sub_flickr_list, sub_flickr_meta = self.flickr.get_photos_info(folder)
            sub_upload_set, sub_base_set = self.diff_flickr(
                sub_dropbox_list,
                sub_flickr_list
            )
            photoset_id = flickr_meta[folder]['id']
            self._sync_flickr_leaf(folder, photoset_id, sub_upload_set)

    def _sync_flickr_root(self, folder):
        file_set = self.dropbox.download_folder(folder)
        logger.debug(file_set)
        photo_id_list = []
        for f in file_set:
            photo_id_list.append(
                self.flickr.upload_photo(folder, f)
            )
        if photo_id_list:  # Not a empty folder
            photoset_id = self.flickr.create_photoset(folder, photo_id_list[0])
            for photo_id in photo_id_list[1:]:
                self.flickr.add_photo_to_photoset(photoset_id, photo_id)

    def _sync_flickr_leaf(self, folder, photoset_id, file_set):
        file_set = self.dropbox.download_folder(folder, file_set)
        logger.debug(file_set)
        photo_id_list = []
        for f in file_set:
            photo_id_list.append(
                self.flickr.upload_photo(folder, f)
            )
        for photo_id in photo_id_list:
            self.flickr.add_photo_to_photoset(photoset_id, photo_id)

    def diff_flickr(self, dropbox_file_set, flickr_file_set):
        # folder_queue = []
        logger.debug('dropbox: ' + str(dropbox_file_set))
        logger.debug('flickr: ' + str(flickr_file_set))

        upload_set = dropbox_file_set.difference(flickr_file_set)
        base_set = dropbox_file_set.difference(upload_set)
        logger.debug('upload_set: ' + str(upload_set))
        logger.debug('base_set: ' + str(base_set))
        return upload_set, base_set


class Dropbox(object):

    def __init__(
        self, api_key, api_secret, app_token, current_path
    ):
        self.api_token = api_key
        self.api_secret = api_secret
        self.app_token = app_token
        self.current_path = current_path

        self.api_client = client.DropboxClient(app_token)

        global TMP_DIR
        TMP_DIR = (tempfile.gettempdir() + os.sep +
                   'cacasync' + os.sep + app_token)
        self._create_tmp_dir()

    def _create_tmp_dir(self):
        if os.path.exists(TMP_DIR):
            if not os.path.isdir(TMP_DIR):
                logger.error('{path} is not a directory'.format(path=TMP_DIR))
                sys.exit(1)
        else:
            os.makedirs(TMP_DIR)

    def ls(self, path=''):
        resp = self.api_client.metadata(
            self.current_path + os.sep + path
        )
        file_set = set()
        file_meta = {}
        if 'contents' in resp:
            for f in resp['contents']:
                path_tokens = f['path'].split(os.sep)
                name = os.sep.join(path_tokens[-1:])
                # encoding = locale.getdefaultlocale()[1]
                file_set.add(name)
                file_meta[name] = {
                    'is_dir': f['is_dir'],
                }
        return file_set, file_meta

    def download_file(self, from_path, to_path):
        """
        Copy file from Dropbox to local file and print out the metadata.

        Examples:
        Dropbox> get file.txt ~/dropbox-file.txt
        """
        to_file = open(os.path.expanduser(to_path), 'wb')
        logger.debug(os.path.expanduser(to_path))

        f, metadata = self.api_client.get_file_and_metadata(
            self.current_path + os.sep + from_path
        )
        # print 'Metadata:', metadata
        to_file.write(f.read())

    def download_folder(self, from_path, file_set=None):
        if file_set is None:
            file_set, file_meta = self.ls(from_path)
        logger.debug(file_set)
        to_path = TMP_DIR + os.sep + from_path
        if os.path.exists(to_path):
            shutil.rmtree(to_path)
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
        self.upload_url = 'http://up.flickr.com/services/upload/'

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
        print(tmp_sig)
        api_sig = md5.new(tmp_sig.encode('utf-8')).hexdigest()
        return ('api_sig', api_sig)

    def get_photosets_info(self):
        args = self._get_request_args(
            method='flickr.photosets.getList'
        )
        resp = requests.post(self.rest_url, data=args)
        logger.debug(resp.text)
        resp_json = json.loads(resp.text.encode('utf-8'))
        photosets = resp_json['photosets']['photoset']
        file_meta = {}
        titles = set()
        for photoset in photosets:
            title = photoset['title']['_content']
            file_meta[title] = {
                'id': photoset['id'],
            }
            titles.add(title)
        self.photoset_titles = titles
        self.photosets_file_meta = file_meta
        return titles, file_meta

    def get_photos_info(self, photoset_name):
        photoset_id = self.photosets_file_meta[photoset_name]['id']
        args = self._get_request_args(
            method='flickr.photosets.getPhotos',
            photoset_id=photoset_id
        )
        resp = requests.post(self.rest_url, data=args)
        logger.debug(resp.text)
        resp_json = json.loads(resp.text.encode('utf-8'))
        photos = resp_json['photoset']['photo']
        file_meta = {}
        titles = set()
        for photo in photos:
            file_meta[photo['title']] = {
                'id': photo['id'],
            }
            titles.add(photo['title'])
        return titles, file_meta

    def upload_photo(self, folder, photo_name):
        args = [
            ('api_key', self.api_key),
            ('auth_token', self.app_token),
            ('tilte', photo_name),
        ]
        args.sort(key=lambda tup: tup[0])
        api_sig = self._get_api_sig(args)
        args.append(api_sig)

        file_path = TMP_DIR + os.sep + folder + os.sep + photo_name
        logger.debug('upload image: ' + file_path)
        files = {
            'photo': open(file_path, 'rb'),
        }
        resp = requests.post(self.upload_url, data=args, files=files)
        logger.debug('upload response: ' + resp.text)
        resp_xml = minidom.parseString(resp.text)
        rsp = resp_xml.getElementsByTagName('rsp')[0]
        if rsp.attributes['stat'].value == 'fail':
            err = resp_xml.getElementsByTagName('err')[0]
            logger.error(err.attributes['msg'].value)
            sys.exit(1)
        elif rsp.attributes['stat'].value == 'ok':
            photo_id = resp_xml.getElementsByTagName('photoid')[0]
            photo_id = photo_id.childNodes[0].nodeValue
            return photo_id
        else:
            logger.error('Unknown error when uploading photos')
            sys.exit(1)

    def create_photoset(self, photoset_name, primary_photo_id):
        args = self._get_request_args(
            method='flickr.photosets.create',
            title=photoset_name,
            primary_photo_id=primary_photo_id
        )
        resp = requests.post(self.rest_url, data=args)
        logger.debug(resp.text)
        resp_json = json.loads(resp.text)
        photoset_id = resp_json['photoset']['id']
        return photoset_id

    def add_photo_to_photoset(self, photoset_id, photo_id):
        args = self._get_request_args(
            method='flickr.photosets.addPhoto',
            photoset_id=photoset_id,
            photo_id=photo_id
        )
        resp = requests.post(self.rest_url, data=args)
        logger.debug(resp.text)


def main():
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(logging.DEBUG)
    console.setFormatter(formatter)
    logger.addHandler(console)
    logger.setLevel(logging.DEBUG)

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
    # flickr.create_photoset('test', '4837317332')

    cacasync = CaCaSync(dropbox, flickr)
    # print(dropbox.ls('box'))
    cacasync.sync_flickr()


if __name__ == '__main__':
    main()
