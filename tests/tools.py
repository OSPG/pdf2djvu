# encoding=UTF-8

# Copyright © 2009-2022 Jakub Wilk <jwilk@jwilk.net>
#
# This file is part of pdf2djvu.
#
# pdf2djvu is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# pdf2djvu is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.

import ast
import codecs
import collections
import inspect
import locale
import os
import re
import shlex
import subprocess
import sys

from unittest import SkipTest, TestCase

_ppm_re = re.compile(br'P6\s+(\d+)\s+(\d+)\s+255\s(.*)\Z', re.DOTALL)
_pgm_re = re.compile(br'P5\s+(\d+)\s+(\d+)\s+255\n(.*)\Z', re.DOTALL)

class ipc_result:

    def __init__(self, test_case, stdout, stderr, rc):
        self.test_case = test_case
        self.stdout = stdout
        self.stderr = stderr
        self.rc = rc

    def assert_(self, stdout='', stderr='', rc=0):
        if stderr is None:
            pass
        elif isinstance(stderr, re.Pattern):
            self.test_case.assertRegex(self.stderr, stderr)
        else:
            self.test_case.assertEqual(self.stderr, stderr)
        if rc is not None:
            self.test_case.assertEqual(self.rc, rc)
        if stdout is None:
            pass
        elif isinstance(stdout, re.Pattern):
            self.test_case.assertRegex(self.stdout, stdout)
        else:
            self.test_case.assertEqual(self.stdout, stdout)

def _get_locale_for_encoding(encoding):
    encoding = codecs.lookup(encoding).name
    candidates = {
        'utf-8': ['C.UTF-8', 'en_US.UTF-8'],
        'iso8859-1': ['en_US.ISO8859-1'],
    }[encoding]
    old_locale = locale.setlocale(locale.LC_ALL)
    try:
        for new_locale in candidates:
            try:
                locale.setlocale(locale.LC_ALL, new_locale)
            except locale.Error:
                continue
            locale_encoding = locale.getencoding()
            locale_encoding = codecs.lookup(locale_encoding).name
            if encoding == locale_encoding:
                return new_locale
    finally:
        locale.setlocale(locale.LC_ALL, old_locale)
    raise SkipTest(
        'locale {loc} is required'.format(loc=str.join(' or ', candidates))
    )

class case(TestCase):

    _pdf2djvu_command = os.getenv('pdf2djvu') or 'pdf2djvu'
    _feature_cache = {}
    _poppler_version = None

    def get_pdf2djvu_command(self):
        if re.compile(r'\A[a-zA-Z0-9_+/=.,:%-]+\Z').match(self._pdf2djvu_command):
            return (self._pdf2djvu_command,)
        return ('sh', '-c', self._pdf2djvu_command + ' "$@"', 'sh')

    def get_source_path(self, strip_py=False):
        result = inspect.getsourcefile(type(self))
        if strip_py and result.endswith('.py'):
            return result[:-3]
        return result

    def get_pdf_path(self):
        return self.get_source_path(strip_py=True) + '.pdf'

    def get_djvu_path(self):
        return self.get_source_path(strip_py=True) + '.djvu'

    def run_command(self, *commandline, **kwargs):
        binary = kwargs.pop('binary', False)
        env = dict(os.environ,
            MALLOC_CHECK_='3',
            MALLOC_PERTURB_=str(0xA5),
        )
        for key, value in kwargs.items():
            if key.isupper():
                env[key] = value
                continue
            if key == 'encoding':
                env['LC_ALL'] = _get_locale_for_encoding(value)
                continue
            raise TypeError('{key!r} is an invalid keyword argument for this function'.format(key=key))
        env['LANGUAGE'] = 'en'
        display_args = (
            os.fsencode(arg).decode(sys.getfilesystemencoding(), errors='backslashreplace')
            for arg in commandline
        )
        print('$', shlex.join(display_args))
        result = subprocess.run(commandline, capture_output=True, env=env)
        stdout, stderr = result.stdout, result.stderr
        if not binary:
            stdout = stdout.decode('UTF-8')
        stderr = stderr.decode('UTF-8')
        return ipc_result(self, stdout, stderr, result.returncode)

    def _pdf2djvu(self, *args, **kwargs):
        quiet = ('-q',) if kwargs.pop('quiet', True) else ()
        args = self.get_pdf2djvu_command() + quiet + (self.get_pdf_path(),) + args
        result = self.run_command(*args, **kwargs)
        if os.getenv('pdf2djvu_win32'):
            result.stderr = result.stderr.replace('\r\n', '\n')
        if sys.platform.startswith('openbsd'):
            # FIXME: https://github.com/jwilk/pdf2djvu/issues/108
            result.stderr = re.compile(
                r'Magick: Failed to close module [(]"\w*: Invalid handle\"[)].\n'
            ).sub('', result.stderr)
        return result

    def pdf2djvu(self, *args, **kwargs):
        return self._pdf2djvu('-o', self.get_djvu_path(), *args, **kwargs)

    def pdf2djvu_indirect(self, *args):
        return self._pdf2djvu('-i', self.get_djvu_path(), *args)

    def djvudump(self, *args):
        return self.run_command('djvudump', self.get_djvu_path(), *args)

    def djvused(self, expr, **kwargs):
        return self.run_command(
            'djvused',
            '-e', expr,
            self.get_djvu_path(),
            **kwargs
        )

    def print_text(self):
        return self.run_command('djvutxt', self.get_djvu_path())

    def print_outline(self):
        return self.djvused('print-outline')

    def print_ant(self, page):
        return self.djvused('select {0}; print-ant'.format(page))

    def print_meta(self):
        return self.djvused('print-meta')

    def ls(self):
        return self.djvused('ls', encoding='UTF-8')

    def decode(self, mode='color', fmt='ppm'):
        r = self.run_command(
            'ddjvu',
            self.get_djvu_path(),
            '-format={f}'.format(f=fmt),
            '-mode={m}'.format(m=mode),
            '-subsample=1',
            binary=True
        )
        r.assert_(stdout=None)
        reader = dict(ppm=self._read_ppm, pgm=self._read_pgm)[fmt]
        return reader(r.stdout)

    def extract_xmp(self):
        r = self.djvused('output-ant')
        self.assertEqual(r.stderr, '')
        self.assertEqual(r.rc, 0)
        xmp_lines = [line for line in r.stdout.splitlines() if line.startswith('(xmp "')]
        if not xmp_lines:
            return None
        [xmp_line] = xmp_lines
        self.assertEqual(xmp_line[-2:], '")')
        xmp = xmp_line[5:-1]
        xmp = ast.literal_eval(xmp)
        return xmp

    def require_poppler(self, *version):
        if self._poppler_version is None:
            r = self.pdf2djvu('--version')
            r.assert_(stdout=re.compile('^pdf2djvu '), rc=0)
            print(r.stdout)
            match = re.compile('^[+] Poppler ([0-9.]+)$', re.M).search(r.stdout)
            self._poppler_version = tuple(int(x) for x in match.group(1).split('.'))
        if self._poppler_version < version:
            str_version = str.join('.', (str(v) for v in version))
            self.skipTest('Poppler >= {ver} is required'.format(ver=str_version))

    def require_feature(self, feature):
        try:
            feature_enabled = self._feature_cache[feature]
        except KeyError:
            if feature == 'POSIX':
                feature_enabled = not os.getenv('pdf2djvu_win32')
            else:
                r = self.pdf2djvu('--version')
                r.assert_(stdout=re.compile('^pdf2djvu '), rc=0)
                feature_enabled = feature in r.stdout
            self._feature_cache[feature] = feature_enabled
        if not feature_enabled:
            self.skipTest(feature + ' support missing')

    def _read_ppm(self, b):
        match = _ppm_re.match(b)
        self.assertIsNotNone(match)
        (width, height, pixels) = match.groups()
        width = int(width)
        height = int(height)
        pixels = memoryview(pixels)
        pixels = [
            [
                pixels[(i + j):(i + j + 3)].tobytes()
                for i in range(0, width * 3, 3)
            ]
            for j in range(0, len(pixels), width * 3)
        ]
        for line in pixels:
            self.assertEqual(len(line), width)
        self.assertEqual(len(pixels), height)
        return pixels

    def _read_pgm(self, b):
        match = _pgm_re.match(b)
        self.assertIsNotNone(match)
        (width, height, pixels) = match.groups()
        width = int(width)
        height = int(height)
        pixels = memoryview(pixels)
        pixels = [
            pixels[i:(i + width)].tobytes()
            for i in range(0, len(pixels), width)
        ]
        for line in pixels:
            self.assertEqual(len(line), width)
        self.assertEqual(len(pixels), height)
        return pixels

    def assert_uuid_urn(self, uuid):
        return self.assertRegex(
            uuid,
            _uuid_regexp,
        )

def rainbow(width, height):
    from PIL import Image
    from PIL import ImageColor
    image = Image.new('RGB', (width, height))
    pixels = image.load()
    for x in range(width):
        for y in range(height):
            hue = 255 * x // (width - 1)
            luminance = 100 * y // height
            color = ImageColor.getrgb('hsl({hue}, 100%, {lum}%)'.format(hue=hue, lum=luminance))
            pixels[x, y] = color
    return image

def checkboard(width, height):
    from PIL import Image
    image = Image.new('1', (width, height))
    pixels = image.load()
    for x in range(width):
        for y in range(height):
            color = 0xFF * ((x ^ y) & 1)
            pixels[x, y] = color
    return image

def count_colors(image):
    result = collections.defaultdict(int)
    for line in image:
        for pixel in line:
            result[pixel] += 1
    return result

xml_ns = dict(
    dc='http://purl.org/dc/elements/1.1/',
    xmpMM='http://ns.adobe.com/xap/1.0/mm/',
)

def xml_find_text(xml, tag):
    [elem] = xml.findall('.//' + tag, xml_ns)
    return elem.text

_uuid_regexp = (
    r'\Aurn:uuid:XXXXXXXX-XXXX-4XXX-[89ab]XXX-XXXXXXXXXXXX\Z'
    .replace('X', '[0-9a-f]')
)

__all__ = [
    # helper classes:
    'ipc_result',
    'case',
    # image handling:
    'rainbow',
    'checkboard',
    'count_colors',
    # XMP:
    'xml_find_text',
    'xml_ns',
]

# vim:ts=4 sts=4 sw=4 et
