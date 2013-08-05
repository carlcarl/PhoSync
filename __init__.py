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
import time
from xml.dom import minidom
from functools import wraps

logger = logging.getLogger(__name__)
CONF_FILE = 'cacasync.conf'
TMP_DIR = ''
SUPPORT_IMAGE_LIST = [
    'jpeg',
    'jpg',
    'png',
    'gif',
    'bmp',
]


def retry(tries=3, delay=1):
    '''
    Retry decorator, used for network requests like upload or download
    '''
    def deco_retry(f):
        @wraps(f)
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


class UploadError(Exception):
    '''
    Upload Exception
    '''
    FLICKR_UPLOAD_ERROR = 0
    UNKNOWN_ERROR = -1

    def __init__(self, errno, msg):
        self.errno = errno
        self.msg = msg


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
            result = self.flickr.upload_photo(folder, f)
            photo_id_list.append(result)
        if photo_id_list:  # Not a empty folder
            photoset_id = self.flickr.create_photoset(folder, photo_id_list[0])
            for photo_id in photo_id_list[1:]:
                self.flickr.add_photo_to_photoset(photoset_id, photo_id)

    def _sync_flickr_leaf(self, folder, photoset_id, file_set):
        file_set = self.dropbox.download_folder(folder, file_set)
        logger.debug(file_set)
        photo_id_list = []
        for f in file_set:
            result = self.flickr.upload_photo(folder, f)
            photo_id_list.append(result)
        for photo_id in photo_id_list:
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
        logger.debug('dropbox: ' + str(dropbox_file_set))
        logger.debug('flickr: ' + str(flickr_file_set))

        diff_set = dropbox_file_set.difference(flickr_file_set)
        base_set = dropbox_file_set.difference(diff_set)
        logger.debug('diff_set: ' + str(diff_set))
        logger.debug('base_set: ' + str(base_set))
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
                   'cacasync' + os.sep + app_token)
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

    def is_image(self, file_path):
        '''
        Check a file is a image or not.
        Here only use the file extension to check
        Args:
            file_path: Path of the file
        Returns:
            True if is a image, else False
        '''
        file_name, file_extension = os.path.splitext(file_path)
        return file_extension.lower() in SUPPORT_IMAGE_LIST

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
                if f['is_dir'] or (not self.is_image(f['path'])):
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
        logger.debug(os.path.expanduser(to_path))

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

        self.photosets_file_meta = None
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
            print(kwargs)
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
        print(tmp_sig)
        api_sig = md5.new(tmp_sig.encode('utf-8')).hexdigest()
        return ('api_sig', api_sig)

    def get_photosets_info(self):
        '''
        Get flickr photosets information
        Returns:
            tltles: Photoset name list
            file_meta: A dict for photoset name to it's other information,
                ex: {'photoset_name': {'id':'aaaaaa'}}
        '''
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
        '''
        Get flickr photos information in the photoset
        Returns:
            tltles: Photo name list
            file_meta: A dict for photo name to it's other information,
                ex: {'photo_name': {'id':'aaaaaa'}}
        '''
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

    @retry()
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
        logger.debug(resp.text)
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
    dropbox_photo_path = parser.get('dropbox', 'CURRENT_PATH')

    dropbox = Dropbox(
        dropbox_api_key,
        dropbox_api_secret,
        dropbox_app_token,
        dropbox_photo_path
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
    cacasync.sync_flickr()


if __name__ == '__main__':
    main()
