"""INCF XNAT prearchive module"""

import httplib
import urllib
import json

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

auth = open('/home/ch/.xnat_pw').read().strip().encode('base64').strip()
host = 'xnat.incf.org'

def _get_session_dict(project, timestamp, name):
    url = '/data/prearchive/projects/%s/%s/%s?format=json' % (project, 
                                                              timestamp, 
                                                              name)
    data = request('GET', url)
    return json.loads(data)['ResultSet']['Result'][0]

class Session:

    def __init__(self, *args):

        """constructor for Sessions

        Session(project, timestamp, name)
        -or- 
        Session(dict) where dict is a dictionary of the XNAT JSON results 
        for a prearchive query
        """

        if len(args) == 1:
            d = args[0]
            if not isinstance(d, dict):
                raise TypeError, 'Session expects a dictionary or three strings'
        elif len(args) == 3:
            for arg in args:
                if not isinstance(arg, basestring):
                    raise TypeError, \
                          'Session expects a dictionary or three strings'
            d = _get_session_dict(args[0], args[1], args[2])
        else:
            raise TypeError, 'Session expects a dictionary or three strings'
        self._update_dict(d)
        return

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

    def __str__(self):
        return '<prearchive session for %s %s %s>' % (self.project, 
                                                      self.timestamp, 
                                                      self.name)

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
