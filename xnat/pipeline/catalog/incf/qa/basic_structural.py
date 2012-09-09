#!/usr/bin/python

import sys
import os
import tempfile
import shutil
import datetime
import subprocess
import xml.dom.minidom
import pyxnat

def attr_value(attrs, name, default=None):
    for (n, v) in attrs:
        if n == name:
            return v
    return default

def append_text_element(doc, parent, name, value):
    el = doc.createElement(name)
    el.appendChild(doc.createTextNode(value))
    parent.appendChild(el)
    return

def append_ind_rel_element(doc, parent, name, ind_val, rel_grand_mean_val):
    """append an element of type NVolsIndRelData"""
    el = doc.createElement(name)
    el.setAttribute('individual', ind_val)
    el.setAttribute('rel_grand_mean', rel_grand_mean_val)
    parent.appendChild(el)
    return

def append_data(doc, parent, birn_parser, element_name, data_name):
    el = doc.createElement(element_name)
    el.setAttribute('absolute_mean', birn_parser.data[data_name]['abs_mean'])
    el.setAttribute('relative_mean', birn_parser.data[data_name]['rel_mean'])
    parent.appendChild(el)
    return

progname = os.path.basename(sys.argv[0])

if len(sys.argv) != 7:
    print 'usage: %s <user> <password> <XNAT URL> <project> <experiment ID> <experiment label>' % progname
    sys.exit(0)

user = sys.argv[1]
password = sys.argv[2]
host = sys.argv[3].rstrip('/')
project_name = sys.argv[4]
experiment_id = sys.argv[5]
experiment_label = sys.argv[6]

interface = pyxnat.Interface(host, user, password)

# interface.select() will return an iterable that doesn't support indexing, so 
# we have to be explicit here
experiment = None
for e in interface.select('/experiments/%s' % experiment_id):
    if e.exists():
        experiment = e
if not experiment:
    sys.stderr.write('%s: can\'t find experiment %s\n' % (progname, 
                                                          experiment_id))
    sys.exit(1)

data_dir = '/data/archive/%s/arc001/%s' % (project_name, experiment_label)

def fp_files(data_dir, scan, resource_name):
    res_dir = '%s/SCANS/%s/%s' % (data_dir, scan.label(), resource_name)
    fp_fnames = []
    for f in files(data_dir, scan, resource_name):
        fp_fnames.append('%s/%s' % (res_dir, f))
    return fp_fnames

def files(data_dir, scan, resource_name):
    resource = scan.resource(resource_name)
    if not resource.exists():
        raise ValueError, 'scan %s has no resource %s' % (scan.label(), 
                                                          resource_name)
    return [ file.label() for file in resource.files() ]

class QATemporaryDirectory:

    def __enter__(self):
        self.path = tempfile.mkdtemp()
        self.clean = True
        fo = open('%s/info' % self.path, 'w')
        fo.write('%s\n' % sys.argv[0])
        fo.write('%s\n' % str(datetime.datetime.now()))
        fo.close()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.clean:
            shutil.rmtree(self.path)
        print 'leaving %s' % self.path
        return

def check_call_stdout(args):
    p = subprocess.Popen(args, stdout=subprocess.PIPE)
    stdout = p.communicate()[0]
    if p.returncode != 0:
        msg = '%s call returned %d' % (args[0], p.returncode)
        raise subprocess.CalledProcessError(p.returncode, args)
    return stdout

def append_stats(doc, root, region, vals):
    el = doc.createElement('BasicStructuralQAStats')
    el.setAttribute('region', region)
    tags = ('RobustMinIntensity', 
            'RobustMaxIntensity', 
            'MinIntensity', 
            'MaxIntensity', 
            'MeanIntensity', 
            'StdIntensity', 
            'NVoxels', 
            'Volume')
    for (tag, val) in zip(tags, vals.split()):
        val = '%.2f' % float(val)
        append_text_element(doc, el, tag, val)
    root.appendChild(el)
    return

with QATemporaryDirectory() as co:
    for scan in experiment.scans():
        print scan.label()
        scan_type = scan.attrs.get('type')
        print 'type is %s' % scan_type
        if scan_type != 'MPRAGE':
            print 'skipping'
            continue
        assessment_name = 'BasicStructuralQA-%s' % scan.label()
        assessment = experiment.assessor(assessment_name)
        if assessment.exists():
            print 'assessment %s exists; skipping' % assessment_name
            continue
        try:
            nifti_files = fp_files(data_dir, scan, 'NIfTI')
        except ValueError:
            continue
        if not nifti_files:
            print 'no NIfTI files'
            continue
        nifti_file = nifti_files[0]
        scan_tempdir = '%s/%s' % (co.path, scan.label())
        os.mkdir(scan_tempdir)

        tissue_stats = {}

#        external_stats = '0.000000 381.000000 0.000000 68.198997 4.351732 27.713835 7803910 9364692.372119'
#        brain_stats = '0.000000 1109.000000 21.070999 398.131012 175.895666 90.608030 1620041 1944049.277250'
#        tissue_stats['csf'] = '1.000000 1109.000000 6.540000 460.820007 88.254002 104.979207 284580 341496.013570'
#        tissue_stats['gm'] = '75.000000 303.000000 91.872002 207.011993 140.452591 29.985393 753119 903742.835912'
#        tissue_stats['wm'] = '154.000000 501.000000 181.759995 416.332001 264.649799 55.033397 582148 698577.627759'

        try:
            shutil.copy(nifti_file, '%s/anat.nii.gz' % scan_tempdir)
            args = ['bet', '%s/anat' % scan_tempdir, 
                    '%s/anat_brain' % scan_tempdir, 
                    '-A', '-m']
            subprocess.check_call(args)
            args = ['fslmaths', '%s/anat_brain_outskin_mask' % scan_tempdir, 
                    '-sub', '1', 
                    '-mul', '-1', 
                    '%s/external' % scan_tempdir]
            subprocess.check_call(args)
            args = ['fast', '-t', '1', '%s/anat_brain' % scan_tempdir]
            subprocess.check_call(args)
            args = ['fslstats', '%s/anat' % scan_tempdir, 
                    '-k', '%s/external' % scan_tempdir, 
                    '-R', '-r', '-m', '-s', '-v']
            external_stats = check_call_stdout(args)
            args = ['fslstats', '%s/anat' % scan_tempdir, 
                    '-k', '%s/anat_brain_mask' % scan_tempdir, 
                    '-R', '-r', '-m', '-s', '-v']
            brain_stats = check_call_stdout(args)
            for (index, tissue) in (('1', 'csf'), ('2', 'gm'), ('3', 'wm')):
                args = ['fslmaths', '%s/anat_brain_seg' % scan_tempdir, 
                        '-thr', index, 
                        '-uthr', index, 
                        '-bin', tissue]
                subprocess.check_call(args)
                args = ['fslstats', '%s/anat' % scan_tempdir, 
                        '-k', tissue, 
                        '-R', '-r', '-m', '-s', '-v']
                tissue_stats[tissue] = check_call_stdout(args)
        except subprocess.CalledProcessError, data:
            print str(data)
            continue

        doc = xml.dom.minidom.Document()
        root = doc.createElement('incf:BasicStructuralQA')
        doc.appendChild(root)
        root.setAttribute('xmlns:incf', 'http://xnat.incf.org/xnat')
        root.setAttribute('xmlns:xnat', 'http://nrg.wustl.edu/xnat')
        root.setAttribute('ID', '')

        append_text_element(doc, root, 'xnat:imageSession_ID', experiment_id)
        append_text_element(doc, root, 'source_scan', scan.label())

        signal = float(brain_stats.split()[4])
        noise = float(external_stats.split()[5])
        if noise != 0.0:
            snr = signal / noise
            append_text_element(doc, root, 'SNR', str(snr))

        append_stats(doc, root, 'external', external_stats)
        append_stats(doc, root, 'brain', brain_stats)
        append_stats(doc, root, 'csf', tissue_stats['csf'])
        append_stats(doc, root, 'gm', tissue_stats['gm'])
        append_stats(doc, root, 'wm', tissue_stats['wm'])

        assessment_xml = '%s/assessment.xml' % scan_tempdir
        print 'creating xml %s...' % assessment_xml
        fo = open(assessment_xml, 'w')
        fo.write(doc.toxml())
        fo.close()

        print 'creating assessment %s...' % assessment_name
        assessment.create(xml=assessment_xml)

sys.exit(0)

# eof
