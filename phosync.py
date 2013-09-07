#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import shutil
import tempfile
import logging
import argparse
from ConfigParser import SafeConfigParser
from dropbox import client
import requests
import md5
import json
import time
import uniout
assert uniout
from xml.dom import minidom

logger = logging.getLogger(__name__)
CONF_FILE = 'phosync.conf'
TMP_DIR = ''
SUPPORT_MIME_LIST = [
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/x-ms-bmp',
]
IMAGE_SIZE_LIMIT = 10485760  # bytes == 10MB


def retry(tries=3, delay=1):
    '''
    Retry decorator, used for network requests like upload or download
    '''
    def deco_retry(f):
        def retry(*args, **kwargs):
            _tries, _delay = tries, delay
            while _tries > 1:
                try:
                    result = f(*args, **kwargs)
                except UploadError as e:
                    logging.error(
                        '[{f}] {msg}, retry...'.format(
                            f=f.__name__,
                            msg=e.msg
                        )
                    )
                    time.sleep(_delay)
                    _tries -= 1
                else:
                    return result
            try:
                result = f(*args, **kwargs)
            except UploadError as e:
                logger.critical(
                    '[{f}] {msg}, program exit'.format(
                        f=f.__name__,
                        msg=e.msg
                    )
                )
                sys.exit(1)
            else:
                return result
        return retry
    return deco_retry


def legal_image(file_info):
    logger.debug('Image size: ' + file_info['size'])
    return is_image(file_info['mime_type']) and legal_image_size(file_info['size'])


def is_image(mime_type):
    '''
    Check a mime type is a image or not.
    Args:
        mime_type: mime type string, ex: image/png
    Returns:
        True if is a image, else False
    '''
    return mime_type in SUPPORT_MIME_LIST


def legal_image_size(size_string):
    size_array = size_string.split(' ')
    size = float(size_array[0])
    unit = size_array[1]
    if unit == 'KB':
        size *= 1024
    elif unit == 'MB':
        size *= 1048576
    is_smaller = size <= IMAGE_SIZE_LIMIT
    if not is_smaller:
        logger.warning('Image size too large: {s}'.format(s=size))
    return is_smaller


class UploadError(Exception):
    '''
    Upload Exception
    '''
    FLICKR_UPLOAD_ERROR = 0
    UNKNOWN_ERROR = -1

    def __init__(self, errno, msg):
        self.errno = errno
        self.msg = msg


class PhoSync(object):

    def __init__(self, dropbox, flickr=None, gplus=None):
        self.dropbox = dropbox
        self.flickr = flickr
        self.gplus = gplus

    def sync_flickr(self):
        dropbox_file_names, dropbox_file_metas = self.dropbox.ls()
        flickr_photoset_titles, flickr_photoset_metas = self.flickr.get_photosets_info()
        diff_set, base_set = self.diff_flickr(
            dropbox_file_names,
            flickr_photoset_titles
        )
        for folder in diff_set:
            self._sync_flickr_root(folder)
        for folder in base_set:
            s_dropbox_file_names, s_dropbox_file_metas = self.dropbox.ls(folder)
            s_flickr_photoset_titles, s_flickr_photoset_metas = self.flickr.get_photos_info(folder)
            s_diff_set, s_base_set = self.diff_flickr(
                s_dropbox_file_names,
                s_flickr_photoset_titles
            )
            photoset_id = flickr_photoset_metas[folder]['id']
            self._sync_flickr_leaf(folder, photoset_id, s_diff_set)

    def _sync_flickr_root(self, folder):
        file_set = self.dropbox.download_folder(folder)
        logger.debug('dropbox download at root: ' + str(file_set))
        flickr_photo_ids = []
        for f in file_set:
            photo_id = self.flickr.upload_photo(folder, f)
            flickr_photo_ids.append(photo_id)
        if flickr_photo_ids:  # Not a empty folder
            photoset_id = self.flickr.create_photoset(folder, flickr_photo_ids[0])
            for photo_id in flickr_photo_ids[1:]:
                self.flickr.add_photo_to_photoset(photoset_id, photo_id)

    def _sync_flickr_leaf(self, folder, photoset_id, file_set):
        file_set = self.dropbox.download_folder(folder, file_set)
        logger.debug('dropbox download at leaf: ' + str(file_set))
        photo_ids = []
        for f in file_set:
            photo_id = self.flickr.upload_photo(folder, f)
            photo_ids.append(photo_id)
        for photo_id in photo_ids:
            self.flickr.add_photo_to_photoset(photoset_id, photo_id)

    def diff_flickr(self, dropbox_file_set, flickr_file_set):
        '''
        Get the different and same part of dropbox and flickr file list
        Args:
            dropbox_file_set: Dropbox file sets
            flickr_file_set: Flickr file sets
        Returns:
            diff_set: Different part
            base_set: Same part
        '''
        # folder_queue = []
        logger.debug('=====================================')
        logger.debug('dropbox: ' + str(dropbox_file_set))
        logger.debug('flickr: ' + str(flickr_file_set))

        diff_set = dropbox_file_set.difference(flickr_file_set)
        base_set = dropbox_file_set.difference(diff_set)
        logger.debug('diff_set: ' + str(diff_set))
        logger.debug('base_set: ' + str(base_set))
        logger.debug('=====================================')
        return diff_set, base_set


class Dropbox(object):
    def __init__(
        self, api_key, api_secret, app_token, photo_path
    ):
        '''
        Args:
            api_key: API key string
            api_secret: API secret string
            app_token: User auth token
            photo_path: Photo path of Dropbox
        '''
        self.api_token = api_key
        self.api_secret = api_secret
        self.app_token = app_token
        self.photo_path = photo_path

        self.api_client = client.DropboxClient(app_token)

        global TMP_DIR
        TMP_DIR = (tempfile.gettempdir() + os.sep +
                   'phosync' + os.sep + app_token)
        self._create_tmp_dir()

    def _create_tmp_dir(self):
        '''
        Create tmp dir recursively, exit if fail
        '''
        if os.path.exists(TMP_DIR):
            if not os.path.isdir(TMP_DIR):
                logger.error('{path} is not a directory'.format(path=TMP_DIR))
                sys.exit(1)
        else:
            os.makedirs(TMP_DIR)

    def ls(self, path=''):
        '''
        List the files under the path.
        The path is under the `photo_path`, ex:
            photo_path='Photos', path='test'
            This method will list all files under 'Photos/test'
        Args:
            path: path string, default is ''
        Returns:
            file_set: Dropbox file set
            file_meta: A dict for dropbox file name to it's other information,
                ex: {'file_name': {'id':'aaaaaa', 'is_dir: False}}
        '''
        resp = self.api_client.metadata(
            self.photo_path + os.sep + path
        )
        file_set = set()
        file_meta = {}
        if 'contents' in resp:
            for f in resp['contents']:
                if (not f['is_dir']) and (not legal_image(f)):
                    continue
                path_tokens = f['path'].split(os.sep)
                name = os.sep.join(path_tokens[-1:])
                file_set.add(name)
                file_meta[name] = {
                    'is_dir': f['is_dir'],
                }
        return file_set, file_meta

    def download_file(self, from_path, to_path):
        '''
        Copy file, metadata from Dropbox to local file, ex:
            from_path='Photo/test/test.jpg', to_path='/tmp/test/test.jpg'
        Args:
            from_path: The file path under `photo_path`
            to_path: The file path where to be saved
        '''
        to_file = open(os.path.expanduser(to_path), 'wb')
        logger.debug('Tmp image path: ' + os.path.expanduser(to_path))

        f, metadata = self.api_client.get_file_and_metadata(
            self.photo_path + os.sep + from_path
        )
        # print 'Metadata:', metadata
        to_file.write(f.read())

    def download_folder(self, from_path, file_set=None):
        '''
        Download a whole folder.
        If `file_set` is not None, then only download the files in the set
        Args:
            from_path: The file path under `photo_path`
            file_set: If is None, download whole folder,
                else only download files in the file_set
        Returns:
            file_set: The downloaded files
        '''
        if file_set is None:
            file_set, file_meta = self.ls(from_path)
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

        self.photoset_metas = None
        self.photoset_titles = None

    def _get_request_args(self, method, **kwargs):
        '''
        Use `method` and other settings to produce a flickr API arguments.
        Here also use json as the return type.
        Args:
            method: The method string provided by flickr,
                ex: flickr.photosets.getPhotos
            **kwargs: Other settings
        Returns:
            args: An argument list used for post request
        '''
        args = [
            ('api_key', self.api_key),
            ('auth_token', self.app_token),
            ('format', 'json'),
            ('method', method),
            ('nojsoncallback', '1'),
        ]
        if kwargs:
            for key, value in kwargs.iteritems():
                args.append((key, value))
        args.sort(key=lambda tup: tup[0])
        api_sig = self._get_api_sig(args)
        args.append(api_sig)
        return args

    def _get_api_sig(self, args):
        '''
        Flickr API need a hash string which made using post arguments
        Args:
            args: Post args(list)
        Returns:
            api_sig: A tuple of api_sig, ex: ('api_sig', 'abcdefg')
        '''
        tmp_sig = self.api_secret
        for i in args:
            tmp_sig = tmp_sig + i[0] + i[1]
        api_sig = md5.new(tmp_sig.encode('utf-8')).hexdigest()
        return ('api_sig', api_sig)

    def get_photosets_info(self):
        '''
        Get flickr photosets information
        Returns:
            tltles: Photoset name list
            photoset_metas: A dict for photoset name to it's other information,
                ex: {'photoset_name': {'id':'aaaaaa'}}
        '''
        args = self._get_request_args(
            method='flickr.photosets.getList'
        )
        resp = requests.post(self.rest_url, data=args)
        logger.debug('Flickr photoset resp: ' + resp.text)
        resp_json = json.loads(resp.text.encode('utf-8'))
        photosets = resp_json['photosets']['photoset']
        photoset_metas = {}
        photoset_titles = set()
        for photoset in photosets:
            title = photoset['title']['_content']
            photoset_metas[title] = {
                'id': photoset['id'],
            }
            photoset_titles.add(title)
        self.photoset_titles = photoset_titles
        self.photoset_metas = photoset_metas
        return photoset_titles, photoset_metas

    def get_photos_info(self, photoset_name):
        '''
        Get flickr photos information in the photoset
        Returns:
            tltles: Photo name list
            photo_metas: A dict for photo name to it's other information,
                ex: {'photo_name': {'id':'aaaaaa'}}
        '''
        if self.photoset_metas is None:
            self.get_photosets_info()
        photoset_id = self.photoset_metas[photoset_name]['id']
        args = self._get_request_args(
            method='flickr.photosets.getPhotos',
            photoset_id=photoset_id
        )
        resp = requests.post(self.rest_url, data=args)
        logger.debug('Flickr photo resp: ' + resp.text)
        resp_json = json.loads(resp.text.encode('utf-8'))
        photos = resp_json['photoset']['photo']
        photo_metas = {}
        photo_titles = set()
        for photo in photos:
            photo_metas[photo['title']] = {
                'id': photo['id'],
            }
            photo_titles.add(photo['title'])
        return photo_titles, photo_metas

    @retry()
    def upload_photo(self, folder, photo_name):
        args = [
            ('api_key', self.api_key),
            ('auth_token', self.app_token),
            ('is_family', '0'),
            ('is_friend', '0'),
            ('is_public', '0'),
            ('tilte', photo_name),
        ]
        args.sort(key=lambda tup: tup[0])
        api_sig = self._get_api_sig(args)
        args.append(api_sig)

        file_path = TMP_DIR + os.sep + folder + os.sep + photo_name
        logger.debug('Flicrk upload image: ' + file_path)
        files = {
            'photo': open(file_path, 'rb'),
        }
        resp = requests.post(self.upload_url, data=args, files=files)
        logger.debug('Flickr upload response: ' + resp.text)
        resp_xml = minidom.parseString(resp.text)
        rsp = resp_xml.getElementsByTagName('rsp')[0]
        if rsp.attributes['stat'].value == 'fail':
            err = resp_xml.getElementsByTagName('err')[0]
            logger.error(err.attributes['msg'].value)
            raise UploadError(
                UploadError.FLICKR_UPLOAD_ERROR,
                err.attributes['msg'].value
            )
        elif rsp.attributes['stat'].value == 'ok':
            photo_id = resp_xml.getElementsByTagName('photoid')[0]
            photo_id = photo_id.childNodes[0].nodeValue
            return photo_id
        else:
            err_msg = 'Unknown error when uploading photos'
            logger.error(err_msg)
            raise UploadError(
                UploadError.UNKNOWN_ERROR,
                err_msg
            )

    def create_photoset(self, photoset_name, primary_photo_id):
        '''
        Create a photoset with a primary photo(cover)
        Args:
            photoset_name: The photoset name
            primary_photo_id: The id of the photo
        Returns:
            photoset_id: The id of the photoset created
        '''
        args = self._get_request_args(
            method='flickr.photosets.create',
            title=photoset_name,
            primary_photo_id=primary_photo_id
        )
        resp = requests.post(self.rest_url, data=args)
        logger.debug('Flickr create photoset resp: ' + resp.text)
        resp_json = json.loads(resp.text)
        photoset_id = resp_json['photoset']['id']
        return photoset_id

    def add_photo_to_photoset(self, photoset_id, photo_id):
        '''
        Add the photo to the photoset
        Args:
            photoset_id: The id of the photoset
            photo_id: The id of the photo
        '''
        args = self._get_request_args(
            method='flickr.photosets.addPhoto',
            photoset_id=photoset_id,
            photo_id=photo_id
        )
        resp = requests.post(self.rest_url, data=args)
        logger.debug(resp.text)


def init_logger():
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(logging.DEBUG)
    console.setFormatter(formatter)
    logger.addHandler(console)
    logger.setLevel(logging.DEBUG)


def _parse_cli_args():
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers()
    ls_parser = subparser.add_parser('ls')
    ls_parser.set_defaults(which='ls')
    ls_parser.add_argument(
        '-d',
        nargs='?',
        default=None,
        const='',
        help='List files in Dropbox under path',
        metavar='<dropbox_path>'
    )
    ls_parser.add_argument(
        '-f',
        nargs='?',
        default=None,
        const='',
        help='List files in Flickr photoset, list all photosets if empty',
        metavar='<flickr photoset>'
    )
    sync_parser = subparser.add_parser('sync')
    sync_parser.set_defaults(which='sync')
    sync_parser.add_argument(
        '-d',
        nargs='?',
        default=None,
        const='',
        help='Sync Dropbox under the path',
        metavar='<dropbox_path>'
    )
    sync_parser.add_argument(
        '-f',
        nargs='?',
        const='',
        help='Flick photoset, sync all if empty',
        metavar='<flickr photoset>'
    )
    args = parser.parse_args()
    logger.debug(args)
    return args


class ConfigReader(object):
    def __init__(self):
        self._parser = SafeConfigParser()
        self._parser.read(CONF_FILE)

    def read(self, service_name, key):
        return self._parser.get(service_name, key)


def init_dropbox(reader_class):
    reader = reader_class()
    dropbox_api_key = reader.read('dropbox', 'APP_KEY')
    dropbox_api_secret = reader.read('dropbox', 'APP_SECRET')

    dropbox_app_token = reader.read('dropbox', 'APP_TOKEN')
    dropbox_photo_path = reader.read('dropbox', 'CURRENT_PATH')

    dropbox = Dropbox(
        dropbox_api_key,
        dropbox_api_secret,
        dropbox_app_token,
        dropbox_photo_path
    )
    return dropbox


def init_flickr(reader_class):
    reader = reader_class()
    flickr_api_key = reader.read('flickr', 'API_KEY')
    flickr_api_secret = reader.read('flickr', 'API_SECRET')

    flickr_app_token = reader.read('flickr', 'APP_TOKEN')
    flickr_app_secret = reader.read('flickr', 'APP_SECRET')

    flickr = Flickr(
        flickr_api_key,
        flickr_api_secret,
        flickr_app_token,
        flickr_app_secret
    )
    return flickr


def ls_command(args):
    if args.d is not None:
        dropbox = init_dropbox(ConfigReader)
        results, _ = dropbox.ls(args.d)
        print(results)
    if args.f is not None:
        flickr = init_flickr(ConfigReader)
        if args.f == '':
            result, _ = flickr.get_photosets_info()
        else:
            result, _ = flickr.get_photos_info(args.f)
        print(result)


def sync_command(args):
    if args.d is not None and args.f is not None:
        dropbox = init_dropbox(ConfigReader)
        flickr = init_flickr(ConfigReader)
        phosync = PhoSync(dropbox, flickr)
        phosync.sync_flickr()


def main():
    init_logger()
    args = _parse_cli_args()
    if args.which == 'ls':
        ls_command(args)
    elif args.which == 'sync':
        sync_command(args)
    # flickr.create_photoset('test', '4837317332')
    # cacasync = CaCaSync(dropbox, flickr)
    # cacasync.sync_flickr()


if __name__ == '__main__':
    main()
