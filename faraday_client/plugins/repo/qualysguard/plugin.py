"""
Faraday Penetration Test IDE
Copyright (C) 2013  Infobyte LLC (http://www.infobytesec.com/)
See the file 'doc/LICENSE' for the license information
"""
from faraday.client.plugins.plugin import PluginXMLFormat
import re
import os
import sys
import logging

try:
    import xml.etree.cElementTree as ET
    import xml.etree.ElementTree as ET_ORIG
    ETREE_VERSION = ET_ORIG.VERSION
except ImportError:
    import xml.etree.ElementTree as ET
    ETREE_VERSION = ET.VERSION

ETREE_VERSION = [int(i) for i in ETREE_VERSION.split('.')]

logger = logging.getLogger(__name__)

current_path = os.path.abspath(os.getcwd())

__author__ = 'Francisco Amato'
__copyright__ = 'Copyright (c) 2013, Infobyte LLC'
__credits__ = ['Francisco Amato']
__license__ = ''
__version__ = '1.0.0'
__maintainer__ = 'Francisco Amato'
__email__ = 'famato@infobytesec.com'
__status__ = 'Development'


def cleaner_unicode(string):
    if string is not None:
        return string.encode('ascii', errors='backslashreplace')
    else:
        return string


def cleaner_results(string):

    try:
        result = string.replace('<P>', '').replace('<UL>', ''). \
            replace('<LI>', '').replace('<BR>', ''). \
            replace('<A HREF="', '').replace('</A>', ' '). \
            replace('" TARGET="_blank">', ' ').replace('&quot;', '"')
        return result

    except:
        return ''


class QualysguardXmlParser():
    """
    The objective of this class is to parse an xml file generated by
    the qualysguard tool.

    TODO: Handle errors.
    TODO: Test qualysguard output version. Handle what happens if the parser
    doesn't support it.
    TODO: Test cases.

    @param qualysguard_xml_filepath A proper xml generated by qualysguard
    """

    def __init__(self, xml_output):
        tree, type_report = self.parse_xml(xml_output)

        if not tree or type_report is None:
            self.items = []
            return

        if type_report is 'ASSET_DATA_REPORT':
            self.items = list(self.get_items_asset_report(tree))
        elif type_report is 'SCAN':
            self.items = list(self.get_items_scan_report(tree))

    def parse_xml(self, xml_output):
        """
        Open and parse an xml file.

        TODO: Write custom parser to just read the nodes that we need instead
        of reading the whole file.

        @return xml_tree An xml tree instance. None if error.
        """

        asset_data_report = '<!DOCTYPE ASSET_DATA_REPORT SYSTEM'
        scan_report = '<!DOCTYPE SCAN SYSTEM'

        try:
            tree = ET.fromstring(xml_output)

            if asset_data_report in xml_output:
                type_report = 'ASSET_DATA_REPORT'
            elif scan_report in xml_output:
                type_report = 'SCAN'
            else:
                type_report = None

        except SyntaxError as err:
            logger.error('SyntaxError: %s.' % (err))
            return None, None

        return tree, type_report

    def get_items_scan_report(self, tree):
        """
        @return items A list of Host instances
        """
        for node in tree.findall('IP'):
            yield ItemScanReport(node)

    def get_items_asset_report(self, tree):
        """
        @return items A list of Host instances
        """
        for node in tree.find('HOST_LIST').findall('HOST'):
            yield ItemAssetReport(node, tree)


class ItemAssetReport():
    """
    An abstract representation of a Item (HOST) for a Asset Report.
    @param item_node A item_node taken from an qualysguard xml tree
    """

    def __init__(self, item_node, tree):

        self.node = item_node
        self.ip = self.get_text_from_subnode('IP')
        self.hostname = self.get_text_from_subnode('DNS') or ''
        self.os = self.get_text_from_subnode('OPERATING_SYSTEM')
        self.vulns = self.getResults(tree)

    def getResults(self, tree):

        glossary = tree.find('GLOSSARY/VULN_DETAILS_LIST')

        for self.issue in self.node.find('VULN_INFO_LIST'):
            yield ResultsAssetReport(self.issue, glossary)

    def get_text_from_subnode(self, subnode_xpath_expr):
        """
        Finds a subnode in the host node and the retrieves a value from it.

        @return An attribute value
        """
        sub_node = self.node.find(subnode_xpath_expr)
        if sub_node is not None:
            return sub_node.text

        return None


class ResultsAssetReport():
    """
    A abstraction of Results for a Asset Report of Qualysguard.
    """

    def __init__(self, issue_node, glossary):

        # VULN_INFO ElementTree
        self.node = issue_node
        self.port = self.get_text_from_subnode(self.node, 'PORT')
        self.protocol = self.get_text_from_subnode(self.node, 'PROTOCOL')
        self.name = self.get_text_from_subnode(self.node, 'QID')
        self.external_id = self.name
        self.result = self.get_text_from_subnode(self.node, 'RESULT')

        self.severity_dict = {
            '1': 'info',
            '2': 'info',
            '3': 'med',
            '4': 'high',
            '5': 'critical'}

        # GLOSSARY TAG
        self.glossary = glossary
        self.severity = self.severity_dict.get(
            self.get_text_from_glossary('SEVERITY'), 'info')
        self.title = self.get_text_from_glossary('TITLE')
        self.cvss = self.get_text_from_glossary('CVSS_SCORE/CVSS_BASE')
        self.pci = self.get_text_from_glossary('PCI_FLAG')
        self.solution = self.get_text_from_glossary('SOLUTION')
        self.impact = self.get_text_from_glossary('IMPACT')

        # Description
        self.desc = cleaner_results(self.get_text_from_glossary('THREAT'))
        if not self.desc:
            self.desc = ''
        if self.result:
            self.desc += '\n\nResult: ' + cleaner_results(self.result)
        if self.impact:
            self.desc += '\n\nImpact: ' + cleaner_results(self.impact)
        if self.result:
            self.desc += '\n\nSolution: ' + cleaner_results(self.solution)

        # References
        self.ref = []

        cve_id = self.get_text_from_glossary('CVE_ID_LIST/CVE_ID/ID')
        if cve_id:
            self.ref.append(cve_id)

        if self.cvss:
            self.ref.append('CVSS SCORE: ' + self.cvss)

        if self.pci:
            self.ref.append('PCI: ' + self.pci)

    def get_text_from_glossary(self, tag):
        """
        Finds a subnode in the glossary and retrieves a value of this.
        Filter by QualysId.

        @return An attribute value
        """

        for vuln_detail in self.glossary:

            id_act = vuln_detail.get('id').strip('qid_')
            if id_act == self.name:

                text = vuln_detail.find(tag)
                if text is not None:
                    return cleaner_unicode(text.text)
                else:
                    return None

    def get_text_from_subnode(self, node, subnode_xpath_expr):
        """
        Finds a subnode in the node and the retrieves a value from it.

        @return An attribute value
        """
        sub_node = node.find(subnode_xpath_expr)
        if sub_node is not None:
            return cleaner_unicode(sub_node.text)

        return None


class ItemScanReport():
    """
    An abstract representation of a Item for a 'SCAN' report of Qualysguard.

    @param item_node A item_node taken from an qualysguard xml tree
    """

    def __init__(self, item_node):
        self.node = item_node
        self.ip = item_node.get('value')
        self.os = self.get_text_from_subnode('OS')
        self.hostname = self.get_hostname(item_node)
        self.vulns = self.getResults(item_node)

    def getResults(self, tree):
        """
        :param tree:
        """
        for self.issues in tree.findall('VULNS/CAT'):
            for v in self.issues.findall('VULN'):
                yield ResultsScanReport(v, self.issues)
        for self.issues in tree.findall('INFOS/CAT'):
            for v in self.issues.findall('INFO'):
                yield ResultsScanReport(v, self.issues)
        for self.issues in tree.findall('SERVICES/CAT'):
            for v in self.issues.findall('SERVICE'):
                yield ResultsScanReport(v, self.issues)
        for self.issues in tree.findall('PRACTICES/CAT'):
            for v in self.issues.findall('PRACTICE'):
                yield ResultsScanReport(v, self.issues)

    def get_text_from_subnode(self, subnode_xpath_expr):
        """
        Finds a subnode in the host node and the retrieves a value from it.

        @return An attribute value
        """
        sub_node = self.node.find(subnode_xpath_expr)
        if sub_node is not None:
            return sub_node.text

        return None

    def get_hostname(self, node):
        hostname = node.get('name')

        if hostname == 'No registered hostname':
            return ""

        return hostname


class ResultsScanReport():
    """
    An abstraction of Result for Qualysguard 'SCAN' Report.
    """

    def __init__(self, issue_node, parent):
        self.node = issue_node
        self.port = parent.get('port')
        self.protocol = parent.get('protocol')
        self.name = self.node.get('number')
        self.external_id = self.node.get('number')
        self.title = self.get_text_from_subnode('TITLE')
        self.cvss = self.get_text_from_subnode('CVSS_BASE')
        self.diagnosis = self.get_text_from_subnode('DIAGNOSIS')
        self.solution = self.get_text_from_subnode('SOLUTION')
        self.result = self.get_text_from_subnode('RESULT')
        self.consequence = self.get_text_from_subnode('CONSEQUENCE')

        self.severity_dict = {
            '1': 'info',
            '2': 'info',
            '3': 'med',
            '4': 'high',
            '5': 'critical'}

        self.severity = self.severity_dict.get(self.node.get('severity'), 'info')

        self.desc = cleaner_results(self.diagnosis)
        if self.result:
            self.desc += '\nResult: ' + cleaner_results(self.result)
        else:
            self.desc += ''

        if self.consequence:
            self.desc += '\nConsequence: ' + cleaner_results(self.consequence)
        else:
            self.desc += ''

        self.ref = []
        for r in issue_node.findall('CVE_ID_LIST/CVE_ID'):
            self.node = r
            self.ref.append(self.get_text_from_subnode('ID'))
        for r in issue_node.findall('BUGTRAQ_ID_LIST/BUGTRAQ_ID'):
            self.node = r
            self.ref.append('bid-' + self.get_text_from_subnode('ID'))

        if self.cvss:
            self.ref.append('CVSS BASE: ' + self.cvss)

    def get_text_from_subnode(self, subnode_xpath_expr):
        """
        Finds a subnode in the host node and the retrieves a value from it.

        @return An attribute value
        """
        sub_node = self.node.find(subnode_xpath_expr)
        if sub_node is not None:
            return cleaner_results(cleaner_unicode(sub_node.text))

        return None


class QualysguardPlugin(PluginXMLFormat):
    """
    Example plugin to parse qualysguard output.
    """

    def __init__(self):
        super().__init__()
        self.identifier_tag = ["ASSET_DATA_REPORT", "SCAN"]
        self.id = 'Qualysguard'
        self.name = 'Qualysguard XML Output Plugin'
        self.plugin_version = '0.0.2'
        self.version = 'Qualysguard 8.17.1.0.2'
        self.framework_version = '1.0.0'
        self.options = None
        self._current_output = None
        self._command_regex = re.compile(
            r'^(sudo qualysguard|\.\/qualysguard).*?')

        global current_path
        self._output_file_path = os.path.join(
            self.data_path,
            'qualysguard_output-%s.xml' % self._rid)

    def parseOutputString(self, output, debug=False):

        parser = QualysguardXmlParser(output)

        for item in parser.items:
            h_id = self.createAndAddHost(
                item.ip,
                item.os,
                hostnames=[item.hostname])

            for v in item.vulns:
                if v.port is None:
                    self.createAndAddVulnToHost(
                        h_id,
                        v.title if v.title else v.name,
                        ref=v.ref,
                        severity=v.severity,
                        resolution=v.solution if v.solution else '',
                        desc=v.desc,
                        external_id=v.external_id)

                else:

                    web = False
                    s_id = self.createAndAddServiceToHost(
                        h_id,
                        v.port,
                        v.protocol,
                        ports=[str(v.port)],
                        status='open')

                    if v.port in ['80', '443'] or re.search('ssl|http', v.name):
                        web = True
                    else:
                        web = False

                    if web:
                        self.createAndAddVulnWebToService(
                            h_id,
                            s_id,
                            v.title if v.title else v.name,
                            ref=v.ref,
                            website=item.ip,
                            severity=v.severity,
                            desc=v.desc,
                            resolution=v.solution if v.solution else '',
                            external_id=v.external_id)

                    else:
                        self.createAndAddVulnToService(
                            h_id,
                            s_id,
                            v.title if v.title else v.name,
                            ref=v.ref,
                            severity=v.severity,
                            desc=v.desc,
                            resolution=v.solution if v.solution else '',
                            external_id=v.external_id)

        del parser

    def processCommandString(self, username, current_path, command_string):
        return None

    def setHost(self):
        pass


def createPlugin():
    return QualysguardPlugin()


# I'm Py3
