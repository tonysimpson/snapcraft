# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright (C) 2015 Canonical Ltd
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import contextlib
import logging
import os
import re

import snapcraft.common
import snapcraft.sources
import snapcraft.repo


logger = logging.getLogger(__name__)


class BasePlugin:

    @classmethod
    def schema(cls):
        '''
        Returns a json-schema for the plugin's properties as a dictionary.
        Of importance to plugin authors is the 'properties' keyword and
        optionally the 'requires' keyword with a list of required
        'properties'.

        By default the the properties will be that of a standard VCS, override
        in custom implementations if required.
        '''
        return {
            '$schema': 'http://json-schema.org/draft-04/schema#',
            'type': 'object',
            'properties': {
                'source': {
                    'type': 'string',
                },
                'source-type': {
                    'type': 'string',
                    'default': '',
                },
                'source-branch': {
                    'type': 'string',
                    'default': '',
                },
                'source-tag': {
                    'type:': 'string',
                    'default': '',
                },
            },
            'required': [
                'source',
            ]
        }

    @property
    def PLUGIN_STAGE_SOURCES(self):
        return getattr(self, '_PLUGIN_STAGE_SOURCES', [])

    def __init__(self, name, options):
        self.name = name
        self.build_packages = []
        self.stage_packages = []

        with contextlib.suppress(AttributeError):
            self.stage_packages = options.stage_packages
        with contextlib.suppress(AttributeError):
            self.build_packages = options.build_packages

        self.options = options
        self.partdir = os.path.join(os.getcwd(), "parts", self.name)
        self.sourcedir = os.path.join(os.getcwd(), "parts", self.name, "src")
        self.builddir = os.path.join(os.getcwd(), "parts", self.name, "build")
        self.ubuntudir = os.path.join(os.getcwd(), "parts", self.name,
                                      'ubuntu')
        self.installdir = os.path.join(os.getcwd(), "parts", self.name,
                                       "install")
        self.stagedir = os.path.join(os.getcwd(), "stage")
        self.snapdir = os.path.join(os.getcwd(), "snap")

    # The API
    def pull(self):
        return True

    def build(self):
        return True

    def snap_fileset(self):
        """Returns one iteratables of globs specific to the plugin:
            - includes can be just listed
            - excludes must be preceded by -
           For example: (['bin', 'lib', '-include'])"""
        return ([])

    def env(self, root):
        return []

    # Helpers
    def run(self, cmd, cwd=None, **kwargs):
        if cwd is None:
            cwd = self.builddir
        if True:
            print(' '.join(cmd))
        self.makedirs(cwd)
        return snapcraft.common.run(cmd, cwd=cwd, **kwargs)

    def run_output(self, cmd, cwd=None, **kwargs):
        if cwd is None:
            cwd = self.builddir
        if True:
            print(' '.join(cmd))
        self.makedirs(cwd)
        return snapcraft.common.run_output(cmd, cwd=cwd, **kwargs)

    def isurl(self, url):
        return snapcraft.common.isurl(url)

    def get_source(self, source, source_type=None, source_tag=None,
                   source_branch=None):
        try:
            handler_class = _get_source_handler(source_type, source)
        except ValueError:
            logger.error("Unrecognized source '%s' for part '%s'.", source,
                         self.name)
            snapcraft.common.fatal()

        try:
            handler = handler_class(source, self.sourcedir, source_tag,
                                    source_branch)
        except snapcraft.sources.IncompatibleOptionsError as e:
            logger.error(
                'Issues while setting up sources for part \'%s\': %s.',
                self.name,
                e.message)
            snapcraft.common.fatal()
        if not handler.pull():
            return False
        return handler.provision(self.builddir)

    def handle_source_options(self):
        stype = getattr(self.options, 'source_type', None)
        stag = getattr(self.options, 'source_tag', None)
        sbranch = getattr(self.options, 'source_branch', None)
        return self.get_source(self.options.source,
                               source_type=stype,
                               source_tag=stag,
                               source_branch=sbranch)

    def makedirs(self, d):
        os.makedirs(d, exist_ok=True)

    def setup_stage_packages(self):
        if self.stage_packages:
            ubuntu = snapcraft.repo.Ubuntu(self.ubuntudir,
                                           sources=self.PLUGIN_STAGE_SOURCES)
            ubuntu.get(self.stage_packages)
            ubuntu.unpack(self.installdir)
            self._fixup(self.installdir)

    def _fixup(self, root):
        if os.path.isfile(os.path.join(root, 'usr', 'bin', 'xml2-config')):
            self.run(
                ['sed', '-i', '-e', 's|prefix=/usr|prefix={}/usr|'.
                    format(root),
                 os.path.join(root, 'usr', 'bin', 'xml2-config')])
        if os.path.isfile(os.path.join(root, 'usr', 'bin', 'xslt-config')):
            self.run(
                ['sed', '-i', '-e', 's|prefix=/usr|prefix={}/usr|'.
                    format(root),
                 os.path.join(root, 'usr', 'bin', 'xslt-config')])


def _get_source_handler(source_type, source):
    if not source_type:
        source_type = _get_source_type_from_uri(source)

    if source_type == 'bzr':
        handler = snapcraft.sources.Bazaar
    elif source_type == 'git':
        handler = snapcraft.sources.Git
    elif source_type == 'mercurial' or source_type == 'hg':
        handler = snapcraft.sources.Mercurial
    elif source_type == 'tar':
        handler = snapcraft.sources.Tar
    else:
        handler = snapcraft.sources.Local

    return handler


def _get_source_type_from_uri(source):
    source_type = ''
    if source.startswith("bzr:") or source.startswith("lp:"):
        source_type = 'bzr'
    elif source.startswith("git:"):
        source_type = 'git'
    elif re.compile(r'.*\.((tar\.(xz|gz|bz2))|tgz)$').match(source):
        source_type = 'tar'
    elif snapcraft.common.isurl(source):
        raise ValueError()

    return source_type
