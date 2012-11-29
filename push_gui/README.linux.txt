INCF Push 1.0
November 29, 2012
Christian Haselgrove
http://xnat.incf.org/

Copyright 2012, Christian Haselgrove
Released under the BSD License: http://opensource.org/licenses/BSD-2-Clause

This program pushes DICOM data to the INCF server as described at
http://xnat.incf.org/.  Unpack incf_push_qt-1.0.tgz, then run
incf_push_qt-1.0/incf_push_qt.  Arguments are paths to directories
containing DICOM data to be uploaded.

Requirements (and their Debian packages):

    PyQt4 (python-qt4) http://www.riverbankcomputing.com/software/pyqt/intro
    DCMTK (dcmtk) http://dicom.offis.de/dcmtk
    httplib2 (python-httplib2) http://code.google.com/p/httplib2/
    pydicom (python-dicom) http://code.google.com/p/pydicom/

