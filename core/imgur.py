"""
Module ported from my previous bot, PenguinBot3000.
"""
from typing import Dict

from imgurpython import ImgurClient

import base64


class Imgur(ImgurClient):
    def __init__(self, imgur_keys: Dict[str, str]):
        client_id = imgur_keys['id']
        client_secret = imgur_keys['secret']
        refresh_token = imgur_keys['refresh']
        access_token = imgur_keys['access']

        super().__init__(client_id, client_secret, access_token, refresh_token)
        self.set_user_auth(access_token, refresh_token)

    # stolen from https://github.com/Imgur/imgurpython
    def upload(self, bytes_str: bytes, config=None, anon=True):
        """
            Takes a file-like object (bytes) and uploads to imgur
        """
        if not config:
            config = dict()

        contents = bytes_str
        b64_str = base64.b64encode(contents)
        data = {
            'image': b64_str,
            'type': 'base64',
        }
        data.update({meta: config[meta] for meta in set(self.allowed_image_fields).intersection(config.keys())})

        return self.make_request('POST', 'upload', data, anon)
