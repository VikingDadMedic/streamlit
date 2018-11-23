# -*- coding: future_fstrings -*-
# Copyright 2018 Streamlit Inc. All rights reserved.

"""Handles a connecton to an S3 bucket to send Report data."""

# Python 2/3 compatibility
from __future__ import print_function, division, unicode_literals, absolute_import
from streamlit.compatibility import setup_2_3_shims
setup_2_3_shims(globals())

import base58
import hashlib
import os

import streamlit

from tornado import gen
from streamlit import errors

from streamlit.logger import get_logger
LOGGER = get_logger()


class AbstractCloudStorage(object):
    """Abstract cloud storage class."""

    def __init__(self):
        """Constructor."""
        static_dir = _build_static_dir()
        static_files, md5 = _get_static_files(static_dir)

        self._static_dir = static_dir
        self._static_files = static_files
        self._release_hash = '%s-%s' % (streamlit.__version__,
            base58.b58encode(md5.digest()[:3]).decode("utf-8"))

    def _get_static_dir(self):
        """Return static directory location."""
        return self._static_dir

    @gen.coroutine
    def save_report_files(self, report_id, files, progress_coroutine=None):
        """Save files related to a given report.

        Parameters
        ----------
        report_id : str
            The report's id.

        files : list of tuples
            A list of pairs of the form:

            [
                (filename_1, raw_data_1),
                (filename_2, raw_data_2), etc..
            ]

            ...where filename_x is the relative path to a file, including the
            actual filename.

            The ordering is important! Files will be written in order according
            to this list.

        progress_coroutine : callable | None
            Generator that will be called successively with a number between 0
            and 100 as input, to indicate progress.

        Returns
        -------
        str
            the url for the saved report.

        """
        raise gen.Return('https://foo.com/%s' % report_id)


def _build_static_dir():
    """Return the path to lib/streamlit/static.

    Returns
    -------
    str
        The path.

    """
    module_dir = os.path.dirname(os.path.normpath(__file__))
    streamlit_dir = os.path.normpath(
        os.path.join(module_dir, '..', '..'))

    return os.path.normpath(
        os.path.join(streamlit_dir, 'static'))


def _get_static_files(static_dir):
    """Get files from the static dir.

    Parameters
    ----------
    static_dir : str
        The path to lib/streamlit/static.

    Returns
    -------
    list of 2-tuples
        The 2-tuples are the relative path to a file and the data for that
        file.
    hashlib.HASH
        An MD5 hash of all files in static_dir.

    """
    # Load static files and compute the release hash
    static_files = []
    md5 = hashlib.md5()

    for root, dirnames, filenames in os.walk(static_dir):
        for filename in filenames:
            absolute_name = os.path.join(root, filename)
            relative_name = os.path.relpath(absolute_name, static_dir)
            with open(absolute_name, 'rb') as input:
                file_data = input.read()
                static_files.append((relative_name, file_data))
                md5.update(file_data)

    if not static_files:
        raise errors.NoStaticFiles(
            'Cannot find static files. Run "make build".')

    return static_files, md5
