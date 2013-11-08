# upgrade.py - test the upgrade transaction using RPM
#
# Copyright (C) 2012 Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Will Woods <wwoods@redhat.com>


# For the sake of simplicity, we don't bother with yum here.
import rpm
from rpm._rpm import ts as TransactionSetCore

import os, tempfile
from threading import Thread

from redhat_upgrade_tool import pkgname

import logging
log = logging.getLogger(pkgname+'.upgrade')

from redhat_upgrade_tool import _
from redhat_upgrade_tool.util import df, hrsize

class TransactionSet(object):
    def __init__(self, *args, **kwargs):
        self._ts = TransactionSetCore(*args, **kwargs)

    # Pass through most everything to self._ts
    def __getattr__(self, name):
        return getattr(self._ts, name)

    def run(self, callback, data, probfilter):
        log.debug('ts.run()')
        rv = self._ts.run(callback, data, probfilter)
        problems = self.problems()
        if rv != rpm.RPMRC_OK and problems:
            raise TransactionError(problems)
        return rv

    def check(self, *args, **kwargs):
        self._ts.check(self, *args, **kwargs)
        # NOTE: rpm.TransactionSet throws out all problems but these
        return [p for p in self.problems()
                  if p.type in (rpm.RPMPROB_CONFLICT, rpm.RPMPROB_REQUIRES)]

    def add_install(self, path, key=None, upgrade=False):
        log.debug('add_install(%s, %s, upgrade=%s)', path, key, upgrade)
        if key is None:
            key = path
        fileobj = open(path)
        try:
            retval, header = self.hdrFromFdno(fileobj)
        finally:
            fileobj.close()
        if retval != rpm.RPMRC_OK:
            raise rpm.error("error reading package header")
        if not self.addInstall(header, key, upgrade):
            raise rpm.error("adding package to transaction failed")

    def __del__(self):
        self.closeDB()

probtypes = { rpm.RPMPROB_NEW_FILE_CONFLICT : _('file conflicts'),
              rpm.RPMPROB_FILE_CONFLICT : _('file conflicts'),
              rpm.RPMPROB_OLDPACKAGE: _('older package(s)'),
              rpm.RPMPROB_DISKSPACE: _('insufficient disk space'),
              rpm.RPMPROB_DISKNODES: _('insufficient disk inodes'),
              rpm.RPMPROB_CONFLICT: _('package conflicts'),
              rpm.RPMPROB_PKG_INSTALLED: _('package already installed'),
              rpm.RPMPROB_REQUIRES: _('broken dependencies'),
              rpm.RPMPROB_BADARCH: _('package for incorrect arch'),
              rpm.RPMPROB_BADOS: _('package for incorrect os'),
            }

# --- stuff for doing useful summaries of big sets of problems

probattrs = ('type', 'pkgNEVR', 'altNEVR', 'key', '_str', '_num')
def prob2dict(p):
    dict = {}
    for f in probattrs:
        dict[f] = getattr(p, f)
    return dict

class ProblemSummary(object):
    def __init__(self, probtype, problems):
        self.type = probtype
        self.problems = [p for p in problems if p.type == self.type]
        self.desc = probtypes.get(probtype)
        self.details = self.get_details()

    def get_details(self):
        return None

    def _log_probs(self):
        for p in self.problems:
            log.debug('%s -> "%s"', prob2dict(p), p)

    def __str__(self):
        if self.details:
            return "\n  ".join([self.desc+':'] + self.format_details())
        else:
            return self.desc

class DiskspaceProblemSummary(ProblemSummary):
    def get_details(self):
        needs = dict()
        for p in self.problems:
            (mnt, size) = (p._str, p._num)
            if size > needs.get(mnt,0):
                needs[mnt] = size
        return needs

    def format_details(self):
        return [_("%s needs %s more free space") % (mnt, hrsize(size))
                 for (mnt,size) in self.details.iteritems()]

class DepProblemSummary(ProblemSummary):
    def get_details(self):
        self._log_probs()
        pkgprobs = dict()
        # pkgprobs['installedpkg'] = {'otherpkg1': [req1, req2, ...], ...}
        for p in self.problems:
            # NOTE: p._num is a header reference if p.pkgNEVR is installed
            thispkg, otherpkg, req = p.altNEVR, p.pkgNEVR, p._str
            if thispkg not in pkgprobs:
                pkgprobs[thispkg] = {}
            if otherpkg not in pkgprobs[thispkg]:
                pkgprobs[thispkg][otherpkg] = set()
            pkgprobs[thispkg][otherpkg].add(req)
        return pkgprobs

    def format_details(self):
        return [_("%s requires %s") % (pkg, ", ".join(pkgprob))
                 for (pkg, pkgprob) in self.details.iteritems()]

probsummary = { rpm.RPMPROB_DISKSPACE: DiskspaceProblemSummary,
                rpm.RPMPROB_REQUIRES:  DepProblemSummary,
              }


def summarize_problems(problems):
    summaries = []
    for t in set(p.type for p in problems):
        summarize = probsummary.get(t, ProblemSummary) # get the summarizer
        summaries.append(summarize(t, problems))       # summarize the problem
    return summaries

class TransactionError(Exception):
    def __init__(self, problems):
        self.problems = problems
        self.summaries = summarize_problems(problems)

def pipelogger(pipe, level=logging.INFO):
    logger = logging.getLogger(pkgname+".rpm")
    logger.info("opening pipe")
    fd = open(pipe, 'r')
    try:
        for line in fd:
            if line.startswith('D: '):
                logger.debug(line[3:].rstrip())
            else:
                logger.log(level, line.rstrip())
        logger.info("got EOF")
    finally:
        fd.close()
    logger.info("exiting")

logging_to_rpm = {
    logging.DEBUG:      rpm.RPMLOG_DEBUG,
    logging.INFO:       rpm.RPMLOG_INFO,
    logging.WARNING:    rpm.RPMLOG_WARNING,
    logging.ERROR:      rpm.RPMLOG_ERR,
    logging.CRITICAL:   rpm.RPMLOG_CRIT,
}

class RPMUpgrade(object):
    def __init__(self, root='/', logpipe=True, rpmloglevel=logging.INFO):
        self.root = root
        self.ts = None
        self.logpipe = None
        rpm.setVerbosity(logging_to_rpm[rpmloglevel])
        if logpipe:
            self.logpipe = self.openpipe()

    def setup_transaction(self, pkgfiles, check_fatal=False):
        log.debug("starting")
        # initialize a transaction set
        self.ts = TransactionSet(self.root, rpm._RPMVSF_NOSIGNATURES)
        if self.logpipe:
            self.ts.scriptFd = self.logpipe.fileno()
        # populate the transaction set
        for pkg in pkgfiles:
            try:
                self.ts.add_install(pkg, upgrade=True)
            except rpm.error, e:
                log.warn('error adding pkg: %s', e)
                # TODO: error callback
        log.debug('ts.check()')
        problems = self.ts.check() or []
        if problems:
            log.info("problems with transaction check:")
            for p in problems:
                log.info(p)
            if check_fatal:
                raise TransactionError(problems=problems)

        log.debug('ts.order()')
        self.ts.order()
        log.debug('ts.clean()')
        self.ts.clean()
        log.debug('transaction is ready')
        if problems:
            return TransactionError(problems=problems)

    def openpipe(self):
        log.debug("creating log pipe")
        pipefile = tempfile.mktemp(prefix='rpm-log-pipe.')
        os.mkfifo(pipefile, 0600)
        log.debug("starting logging thread")
        pipethread = Thread(target=pipelogger, name='pipelogger',
                                 args=(pipefile,))
        pipethread.daemon = True
        pipethread.start()
        log.debug("opening log pipe")
        pipe = open(pipefile, 'w')
        rpm.setLogFile(pipe)
        return pipe

    def closepipe(self):
        log.debug("closing log pipe")
        rpm.setVerbosity(rpm.RPMLOG_WARNING)
        rpm.setLogFile(None)
        if self.ts:
            self.ts.scriptFd = None
        self.logpipe.close()
        os.remove(self.logpipe.name)
        self.logpipe = None

    def run_transaction(self, callback):
        assert callable(callback.callback)
        probfilter = ~rpm.RPMPROB_FILTER_DISKSPACE
        rv = self.ts.run(callback.callback, None, probfilter)
        if rv != 0:
            log.info("ts completed with problems - code %u", rv)
        return rv

    def test_transaction(self, callback):
        old_flags = self.ts.setFlags(rpm.RPMTRANS_FLAG_TEST)
        try:
            return self.run_transaction(callback)
        finally:
            self.ts.setFlags(old_flags)

    def __del__(self):
        if self.logpipe:
            self.closepipe()
