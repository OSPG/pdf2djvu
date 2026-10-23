# encoding=UTF-8

# Copyright © 2009-2016 Jakub Wilk <jwilk@jwilk.net>
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

import xml.etree.ElementTree as etree

from tools import (
    case,
    xml_find_text,
)

class test(case):
    # + fixed in 0.6.0 [79d56ebabd600e44f7aa97634d44d471249e74f2]

    def test_verbatim(self):
        self.pdf2djvu('--verbatim-metadata').assert_()
        xmp = self.extract_xmp()
        self.assertIsNone(xmp)

    def test_no_verbatim(self):
        self.require_feature('Exiv2')
        self.pdf2djvu().assert_()
        xmp = self.extract_xmp()
        xmp = etree.fromstring(xmp)
        dcformat = xml_find_text(xmp, 'dc:format')
        self.assertEqual(dcformat, 'image/vnd.djvu')
        instance_id = xml_find_text(xmp, 'xmpMM:InstanceID')
        document_id = xml_find_text(xmp, 'xmpMM:DocumentID')
        self.assertNotEqual(instance_id, document_id)
        self.assert_uuid_urn(instance_id)
        self.assert_uuid_urn(document_id)

# vim:ts=4 sts=4 sw=4 et
