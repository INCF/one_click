"""INCF XNAT prearchive module"""

import os
import httplib
import urllib
import weakref
import smtplib
import xml.dom.minidom
import json
import dicom

auth = open('/home/ch/.xnat_pw').read().strip().encode('base64').strip()
host = 'xnat.incf.org'
mail_host = 'luna.incf.ki.se'

class PrearchiveError(Exception):
    "base class for prearchive exceptions"

class RequestError(PrearchiveError):

    "HTTP (REST) request error"

    def __init__(self, request, response):
        self.request = request
        self.response = response
        return

    def __str__(self):
        return 'RequestError: %d %s' % (self.response.status, \
                                        self.response.reason)

def send_mail(to_addrs, subject, body):
    if not isinstance(to_addrs, (tuple, list)):
        raise TypeError, 'send_mail() expects a tuple or list of recipients'
    if not to_addrs:
        return
    message = email.message.Message()
    message['From'] = from_email
    for addr in to_addrs:
        message['To'] = addr
    message['Subject'] = subject
    message.set_payload(body)
    s = smtplib.SMTP(mail_host)
    s.sendmail(from_email, to_addrs, message.as_string())
    s.quit()
    return

def _get_session_dict(*args):
    """return a dictionary of session information given a url or a project, timestamp, and name"""
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

    def __getattr__(self, name):
        if name == 'dicom':
            self.dicom = dicom.read_file(self.path, stop_before_pixels=True)
            return self.dicom
        raise AttributeError, "_Entry instance has no attribute '%s'" % name

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
        self.id = int(self.node.getAttribute('ID'))
        self.uid = self.node.getAttribute('UID')
        self.type = self.node.getAttribute('xsi:type')
        return

    def __str__(self):
        return '<prearchive scan %d>' % self.id

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
                raise TypeError, 'Session expects a dictionary, one string, or three strings'
        elif len(args) == 3:
            for arg in args:
                if not isinstance(arg, basestring):
                    raise TypeError, \
                          'Session expects a dictionary, one string, or three strings'
            d = _get_session_dict(args[0], args[1], args[2])
        else:
            raise TypeError, 'Session expects a dictionary, one string, or three strings'
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
        if name == 'incf_user':
            self.incf_user = self._get_submitting_user()
            return self.incf_user
        raise AttributeError, "Session instance has no attribute '%s'" % name

    def _get_submitting_user(self):
        "return the INCF username as specified in the study comments or None"
        for s in self.scans:
            for f in s.files:
                if f.format != 'DICOM':
                    continue
                for entry in f.entries:
                    try:
                        (ident, val) = entry.dicom.StudyDescription.split(':', 2)
                        if ident.strip().lower() == 'incf':
                            return val.strip()
                    except:
                        pass
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
        body = urllib.urlencode({'src': self.url})
        request('POST', '/data/services/archive', body)
        return

    def get_errors(self):
        """return a list of errors (like insufficient deidentification) that prevent archiving"""
        raise NotImplementedError

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
    if response.status != 200:
        raise RequestError(request, response)
    data = response.read()
    hc.close()
    return data

# eof
