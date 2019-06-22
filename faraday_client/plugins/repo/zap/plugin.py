#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Faraday Penetration Test IDE
Copyright (C) 2013  Infobyte LLC (http://www.infobytesec.com/)
See the file 'doc/LICENSE' for the license information
'''

from __future__ import with_statement
import re
import os
import socket
import sys
from faraday.client.plugins import core


try:
    import xml.etree.cElementTree as ET
    import xml.etree.ElementTree as ET_ORIG
    ETREE_VERSION = ET_ORIG.VERSION

except ImportError:
    import xml.etree.ElementTree as ET
    ETREE_VERSION = ET.VERSION

ETREE_VERSION = [int(i) for i in ETREE_VERSION.split(".")]

current_path = os.path.abspath(os.getcwd())

__author__ = "Francisco Amato"
__copyright__ = "Copyright (c) 2013, Infobyte LLC"
__credits__ = ["Francisco Amato"]
__license__ = ""
__version__ = "1.0.0"
__maintainer__ = "Francisco Amato"
__email__ = "famato@infobytesec.com"
__status__ = "Development"


class ParserEtToAscii(ET_ORIG.TreeBuilder):

    def data(self, data):
        self._data.append(data.encode("ascii", errors="backslashreplace"))


class ZapXmlParser(object):
    """
    The objective of this class is to parse an xml
    file generated by the zap tool.

    TODO: Handle errors.
    TODO: Test zap output version. Handle what happens
          if the parser doesn't support it.

    TODO: Test cases.

    @param zap_xml_filepath A proper xml generated by zap
    """

    def __init__(self, xml_output):

        tree = self.parse_xml(xml_output)

        if tree is not None:
            self.sites = [data for data in self.get_items(tree)]
        else:
            self.sites = []

    def parse_xml(self, xml_output):
        """
        Open and parse an xml file.

        TODO: Write custom parser to just read the nodes that we need instead of
        reading the whole file.

        @return xml_tree An xml tree instance. None if error.
        """
        try:
            parser = ET_ORIG.XMLParser(target=ParserEtToAscii())
            parser.feed(xml_output)
            tree = parser.close()

        except SyntaxError, err:
            print "SyntaxError: %s. %s" % (err, xml_output)
            return None

        return tree

    def get_items(self, tree):
        """
        @return items A list of Host instances
        """
        for node in tree.findall('site'):
            yield Site(node)


def get_attrib_from_subnode(xml_node, subnode_xpath_expr, attrib_name):
    """
    Finds a subnode in the item node and the retrieves a value from it

    @return An attribute value
    """
    global ETREE_VERSION
    node = None

    if ETREE_VERSION[0] <= 1 and ETREE_VERSION[1] < 3:

        match_obj = re.search(
            "([^\@]+?)\[\@([^=]*?)=\'([^\']*?)\'",
            subnode_xpath_expr)

        if match_obj is not None:

            node_to_find = match_obj.group(1)
            xpath_attrib = match_obj.group(2)
            xpath_value = match_obj.group(3)

            for node_found in xml_node.findall(node_to_find):

                if node_found.attrib[xpath_attrib] == xpath_value:
                    node = node_found
                    break
        else:
            node = xml_node.find(subnode_xpath_expr)

    else:
        node = xml_node.find(subnode_xpath_expr)

    if node is not None:
        return node.get(attrib_name)

    return None


class Site(object):

    def __init__(self, item_node):

        self.node = item_node

        self.host = self.node.get('host')
        self.ip = self.resolve(self.host)
        self.port = self.node.get('port')

        self.items = []
        for alert in self.node.findall('alerts/alertitem'):
            self.items.append(Item(alert))

    def get_text_from_subnode(self, subnode_xpath_expr):
        """
        Finds a subnode in the host node and the retrieves a value from it.

        @return An attribute value
        """
        sub_node = self.node.find(subnode_xpath_expr)
        if sub_node is not None:
            return sub_node.text
        return None

    def resolve(self, host):

        try:
            return socket.gethostbyname(host)
        except:
            pass

        return host


class Item(object):
    """
    An abstract representation of a Item


    @param item_node A item_node taken from an zap xml tree
    """

    def __init__(self, item_node):

        self.node = item_node
        self.id = self.get_text_from_subnode('pluginid')
        self.name = self.get_text_from_subnode('alert')
        self.severity = self.get_text_from_subnode('riskcode')
        self.desc = self.get_text_from_subnode('desc')

        if self.get_text_from_subnode('solution'):
            self.resolution = self.get_text_from_subnode('solution')
        else:
            self.resolution = ''

        if self.get_text_from_subnode('reference'):
            self.desc += '\nReference: ' + \
                self.get_text_from_subnode('reference')

        self.ref = []
        if self.get_text_from_subnode('cweid'):
            self.ref.append("CWE-" + self.get_text_from_subnode('cweid'))

        self.items = []

        if item_node.find('instances'):
            arr = item_node.find('instances')
        else:
            arr = [item_node]

        for elem in arr:
            uri = elem.find('uri').text
            self.parse_uri(uri)

        self.requests = "\n".join([i['uri'] for i in self.items])

    def parse_uri(self, uri):
        mregex = re.search(
            "(http|https|ftp)\://([a-zA-Z0-9\.\-]+(\:[a-zA-Z0-9\.&amp"
            ";%\$\-]+)*@)*((25[0-5]|2[0-4][0-9]|[0-1]{1}[0-9]{2}|[1-9]{1}[0-9]"
            "{1}|[1-9])\.(25[0-5]|2[0-4][0-9]|[0-1]{1}[0-9]{2}|[1-9]{1}[0-9]{1}"
            "|[1-9]|0)\.(25[0-5]|2[0-4][0-9]|[0-1]{1}[0-9]{2}|[1-9]{1}[0-9]{1}"
            "|[1-9]|0)\.(25[0-5]|2[0-4][0-9]|[0-1]{1}[0-9]{2}|[1-9]{1}[0-9]{1}|"
            "[0-9])|localhost|([a-zA-Z0-9\-]+\.)*[a-zA-Z0-9\-]+\.(com|edu|gov|"
            "int|mil|net|org|biz|arpa|info|name|pro|aero|coop|museum|[a-zA-Z]{2"
            "}))[\:]*([0-9]+)*([/]*($|[a-zA-Z0-9\.\,\?\'\\\+&amp;%\$#\=~_\-]+))"
            ".*?$",
            uri)

        protocol = mregex.group(1)
        host = mregex.group(4)
        port = 80
        if protocol == 'https':
            port = 443
        if mregex.group(11) is not None:
            port = mregex.group(11)

        try:
            params = [i.split('=')[0]
                      for i in uri.split('?')[1].split('&')]
        except Exception as e:
            params = ''

        item = {
            'uri': uri,
            'params': ', '.join(params),
            'host': host,
            'protocol': protocol,
            'port': port
        }
        self.items.append(item)


    def get_text_from_subnode(self, subnode_xpath_expr):
        """
        Finds a subnode in the host node and the retrieves a value from it.

        @return An attribute value
        """
        sub_node = self.node.find(subnode_xpath_expr)
        if sub_node is not None:
            return sub_node.text

        return None


class ZapPlugin(core.PluginBase):
    """
    Example plugin to parse zap output.
    """

    def __init__(self):

        core.PluginBase.__init__(self)
        self.id = "Zap"
        self.name = "Zap XML Output Plugin"
        self.plugin_version = "0.0.3"
        self.version = "2.4.3"
        self.framework_version = "1.0.0"
        self.options = None
        self._current_output = None
        self.target = None
        self._command_regex = re.compile(r'^(zap|sudo zap|\.\/zap).*?')

        global current_path

        self._output_file_path = os.path.join(
            self.data_path,
            "zap_output-%s.xml" % self._rid
        )

    def parseOutputString(self, output, debug=False):
        """
        This method will discard the output the shell sends, it will read it
        from the xml where it expects it to be present.

        NOTE: if 'debug' is true then it is being run from a test case and the
        output being sent is valid.
        """

        parser = ZapXmlParser(output)

        for site in parser.sites:

            host = []
            if site.host != site.ip:
                host = [site.host]

            h_id = self.createAndAddHost(site.ip)

            i_id = self.createAndAddInterface(
                h_id,
                site.ip,
                ipv4_address=site.ip,
                hostname_resolution=host
            )

            s_id = self.createAndAddServiceToInterface(
                h_id,
                i_id,
                "http",
                "tcp",
                ports=[site.port],
                status='open'
            )

            n_id = self.createAndAddNoteToService(h_id, s_id, "website", "")
            n2_id = self.createAndAddNoteToNote(
                h_id, s_id, n_id, site.host, "")

            for item in site.items:
                v_id = self.createAndAddVulnWebToService(
                    h_id,
                    s_id,
                    item.name,
                    item.desc,
                    website=site.host,
                    severity=item.severity,
                    path=item.items[0]['uri'],
                    params=item.items[0]['params'],
                    request=item.requests,
                    ref=item.ref,
                    resolution=item.resolution
                )

        del parser

    def processCommandString(self, username, current_path, command_string):
        return None

    def setHost(self):
        pass


def createPlugin():
    return ZapPlugin()

if __name__ == '__main__':
    parser = ZapXmlParser(sys.argv[1])
    for item in parser.items:
        if item.status == 'up':
            print item
