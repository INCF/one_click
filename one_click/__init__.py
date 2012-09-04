# See file COPYING distributed with the one_click package for the copyright 
# and license.

"""INCF XNAT prearchive module"""

import os
import shutil
import httplib
import urllib
import weakref
import smtplib
import email.message
import xml.dom.minidom
import json
import jinja2
import dicom

auth = open('/home/ch/.xnat_pw').read().strip().encode('base64').strip()
host = 'localhost'
mail_host = 'localhost'
admin_email = 'xnat-admin@incf.org'
deleted_dir = '/data/cache/DELETED'

deident_tags = {(0x0008, 0x0050): "Accession Number", 
                (0x0008, 0x0080): "InstitutionName", 
                (0x0008, 0x0090): "Referring Physician's Name", 
                (0x0008, 0x0096): "Referring Physician Identification", 
                (0x0008, 0x1048): "Physician(s) of Record", 
                (0x0008, 0x1049): "Physician(s) of Record Identification", 
                (0x0008, 0x1050): "Performing Physicians' Name", 
                (0x0008, 0x1052): "Performing Physician Identification", 
                (0x0008, 0x1060): "Name of Physician(s) Reading Study", 
                (0x0008, 0x1062): "Physician(s) Reading Study Identification", 
                (0x0010, 0x0030): "Patient's Birth Date", 
                (0x0010, 0x0050): "Patient's Insurance Plan Code", 
                (0x0010, 0x0101): "Patient's Primary Language Code", 
                (0x0010, 0x1000): "Other Patient IDs", 
                (0x0010, 0x1001): "Other Patient Names", 
                (0x0010, 0x1002): "Other Patient IDs", 
                (0x0010, 0x1005): "Patient's Birth Name", 
                (0x0010, 0x1010): "Patient's Age", 
                (0x0010, 0x1040): "Patient's Address", 
                (0x0010, 0x1060): "Patient's Mother's Birth Name"}

class PrearchiveError(Exception):
    "base class for prearchive exceptions"

class RequestError(PrearchiveError):

    "HTTP (REST) request error"

    def __init__(self, request, response, data):
        self.request = request
        self.response = response
        self.data = data
        return

    def __str__(self):
        return 'RequestError: %d %s' % (self.response.status, \
                                        self.response.reason)

class StudyCommentsError(Exception):
    """bad study comments"""

    def __init__(self, msg):
        self.msg = msg
        return

    def __str__(self):
        return self.msg

def parse_study_comments(session):
    info = {}
    if session.study_comments is None:
        raise StudyCommentsError('no study comments')
    # check for the one protocol we know how to parse
    if session.study_comments.split('\n')[0] != 'incf 2':
        raise StudyCommentsError('bad protocol line')
    for line in session.study_comments.split('\n'):
        (key, value) = line.split(' ', 1)
        info[key] = value
    for key in ('upload_agreement', 'user', 'project'):
        if key not in info:
            raise StudyCommentsError('missing required key %s' % key)
    if info['upload_agreement'] != 'signed':
        raise StudyCommentsError('missing signed upload agreement')
    return info

def send_mail(to_addrs, subject, body):
    if not isinstance(to_addrs, (tuple, list)):
        raise TypeError, 'send_mail() expects a tuple or list of recipients'
    if not to_addrs:
        return
    message = email.message.Message()
    message['From'] = admin_email
    for addr in to_addrs:
        message['To'] = addr
    message['Subject'] = subject
    message.set_payload(body)
    s = smtplib.SMTP(mail_host)
    s.sendmail(admin_email, to_addrs, message.as_string())
    s.quit()
    return

def _get_session_dict(*args):
    """return a dictionary of session information given a url or a project, 
    timestamp, and name
    """
    if len(args) == 1:
        url = '/data%s?format=json' % args[0]
    elif len(args) == 3:
        url = '/data/prearchive/projects/%s/%s/%s?format=json' % args
    else:
        raise TypeError, '_get_session_dict() expects one or three strings'
    data = request('GET', url)
    return json.loads(data)['ResultSet']['Result'][0]

def xml_str(node):
    """return the text inside an XML node"""
    s = u''
    for cn in node.childNodes:
        if cn.nodeType == cn.TEXT_NODE:
            s += cn.data
    return s

class _Entry:

    def __init__(self, file, node):
        self.file = weakref.ref(file)
        self.dir = os.path.dirname(file.catalog_path)
        self.uid = node.getAttribute('UID')
        self.uri = node.getAttribute('URI')
        self.instance_number = node.getAttribute('instanceNumber')
        self.type = node.getAttribute('xsi:type')
        self.path = '%s/%s' % (self.dir, self.uri)
        return

    def __str__(self):
        return '<prearchive entry %s>' % self.uri

    def read_dicom(self):
        return dicom.read_file(self.path)

class _File:

    """prearchive session file object

    this class corresponds to the <xnat:file> tag in the prearchive session XML
    """

    def __init__(self, scan, node):
        self.scan = weakref.ref(scan)
        self.uri = node.getAttribute('URI')
        self.content = node.getAttribute('content')
        self.format = node.getAttribute('format')
        self.label = node.getAttribute('label')
        self.type = node.getAttribute('xsi:type')
        # self.scan and .session are weakrefs
        self.catalog_path = '%s/%s' % (self.scan().session().path, self.uri)
        self.node = xml.dom.minidom.parse(self.catalog_path)
        return

    def __str__(self):
        return '<prearchive file %s>' % self.label

    def __getattr__(self, name):
        if name == 'entries':
            self.entries = []
            for node in self.node.getElementsByTagName('cat:entry'):
                self.entries.append(_Entry(self, node))
            return self.entries
        raise AttributeError, "_File instance has no attribute '%s'" % name

class _Scan:

    def __init__(self, session, node):
        self.session = weakref.ref(session)
        self.node = node
        self.id = self.node.getAttribute('ID')
        self.uid = self.node.getAttribute('UID')
        self.type = self.node.getAttribute('xsi:type')
        return

    def __str__(self):
        return '<prearchive scan %s>' % self.id

    def __getattr__(self, name):
        if name == 'files':
            self.files = []
            for node in self.node.getElementsByTagName('xnat:file'):
                self.files.append(_File(self, node))
            return self.files
        raise AttributeError, "_Scan instance has no attribute '%s'" % name

class Session:

    def __init__(self, *args):

        """constructor for Sessions

        Session(project, timestamp, name)
        -or- 
        Session(dict) where dict is a dictionary of the XNAT JSON results 
        for a prearchive query
        """

        if len(args) == 1:
            if isinstance(args[0], dict):
                d = args[0]
            elif isinstance(args[0], basestring):
                d = _get_session_dict(args[0])
            else:
                raise TypeError, 'Session expects a dictionary, ' + \
                                 'one string, or three strings'
        elif len(args) == 3:
            for arg in args:
                if not isinstance(arg, basestring):
                    raise TypeError, \
                          'Session expects a dictionary, ' + \
                          'one string, or three strings'
            d = _get_session_dict(args[0], args[1], args[2])
        else:
            raise TypeError, 'Session expects a dictionary, ' + \
                             'one string, or three strings'
        self._update_dict(d)
        return

    def __str__(self):
        return '<prearchive session for %s %s %s>' % (self.project, 
                                                      self.timestamp, 
                                                      self.name)

    def __getattr__(self, name):
        if name == 'doc':
            data = request('GET', '/data%s' % self.url)
            self.doc = xml.dom.minidom.parseString(data)
            return self.doc
        if name == 'path':
            node = self.doc.getElementsByTagName('xnat:prearchivePath')[0]
            self.path = xml_str(node)
            return self.path
        if name == 'scans':
            self.scans = []
            for node in self.doc.getElementsByTagName('xnat:scan'):
                self.scans.append(_Scan(self, node))
            return self.scans
        if name == 'study_comments':
            self.study_comments = self._get_study_comments()
            return self.study_comments
        raise AttributeError, "Session instance has no attribute '%s'" % name

    def _get_study_comments(self):
        "return the first study description found or None"
        for s in self.scans:
            for f in s.files:
                if f.format != 'DICOM':
                    continue
                for entry in f.entries:
                    try:
                        val = entry.read_dicom().StudyComments
                    except:
                        pass
                    else:
                        return val
        return None

    def _update_dict(self, d):
        "update the session information from a dictionary"
        self.autoarchive = d['autoarchive']
        self.folderName = d['folderName']
        self.lastmod = d['lastmod']
        self.name = d['name']
        self.project = d['project']
        self.scan_date = d['scan_date']
        self.scan_time = d['scan_time']
        self.status = d['status']
        self.subject = d['subject']
        self.tag = d['tag']
        self.timestamp = d['timestamp']
        self.uploaded = d['uploaded']
        self.url = d['url']
        return

    def move(self, new_project):
        """move a session to a different project

        no checking is done on the given project; data may seem to disappear 
        if the project does not exist
        """
        body = urllib.urlencode({'src': self.url, 
                                 'newProject': new_project, 
                                 'async': 'false'})
        request('POST', '/data/services/prearchive/move', body)
        d = _get_session_dict(new_project, self.timestamp, self.name)
        self._update_dict(d)
        return

    def delete(self):
        """delete a session"""
        body = urllib.urlencode({'src': self.url, 'async': 'false'})
        request('POST', '/data/services/prearchive/delete', body)
        return

    def archive(self):
        """archive a session"""
        body = urllib.urlencode({'src': self.url, 'overwrite': 'append'})
        request('POST', '/data/services/archive', body)
        return

    def check_deidentification(self):
        """return a list of DICOM tags that should be removed for proper 
        deidentification
        """
        tags = set()
        for s in self.scans:
            for f in s.files:
                if f.format != 'DICOM':
                    continue
                for entry in f.entries:
                    do = entry.read_dicom()
                    for tag in deident_tags:
                        if tag in do:
                            tags.add(tag)
        tags = list(tags)
        tags.sort()
        return tags

def all_sessions():
    data = request('GET', '/data/prearchive/projects')
    sessions = [ Session(d) for d in json.loads(data)['ResultSet']['Result'] ]
    return sessions

def request(method, url, body=None):
    url = '/xnat%s' % url
    hc = httplib.HTTPConnection(host)
    headers = {'Authorization': 'Basic %s' % auth, 
               'Content-Type': 'application/x-www-form-urlencoded'}
    hc.request(method, url, headers=headers, body=body)
    response = hc.getresponse()
    data = response.read()
    hc.close()
    if response.status != 200:
        raise RequestError(request, response, data)
    return data

def report_error(subject, body):
    send_mail([admin_email], subject, body)
    return

def remove_deleted():
    "removes files marked deleted by XNAT"
    shutil.rmtree(deleted_dir)
    return

template_dir = '%s/templates' % os.path.dirname(__file__)
template_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))

# eof
