#!/usr/bin/python

from distutils.core import setup, Command
from distutils.util import convert_path
from distutils.command.build_scripts import build_scripts
from distutils import log

import os
from os.path import join, basename
from subprocess import call

class CalledProcessError(Exception):
    """From subprocess.CalledProcessError in Python 2.7"""
    def __init__(self, returncode, cmd, output=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
    def __str__(self):
        return "Command '%s' returned non-zero exit status %d" % (self.cmd, self.returncode)

def check_call(*popenargs, **kwargs):
    """From subprocess.check_call in Python 2.7"""
    retcode = call(*popenargs, **kwargs)
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise CalledProcessError(retcode, cmd)
    return 0

class Gettext(Command):
    description = "Use po/POTFILES.in to generate po/<name>.pot"
    user_options = []
    def initialize_options(self):
        self.encoding = 'UTF-8'
        self.po_dir = 'po'
        self.add_comments = True

    def finalize_options(self):
        pass

    def _xgettext(self, opts):
        name = self.distribution.get_name()
        version = self.distribution.get_version()
        email = self.distribution.get_author_email()
        cmd = ['xgettext', '--default-domain', name, '--package-name', name,
               '--package-version', version, '--msgid-bugs-address', email,
               '--from-code', self.encoding,
               '--output', join(self.po_dir, name + '.pot')]
        if self.add_comments:
            cmd.append('--add-comments')
        check_call(cmd + opts)

    def run(self):
        self._xgettext(['-f', 'po/POTFILES.in'])

class Msgfmt(Command):
    description = "Generate po/*.mo from po/*.po"
    user_options = []
    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        po_dir = 'po'
        for po in os.listdir(po_dir):
            po = join(po_dir, po)
            if po.endswith('.po'):
                mo = po[:-3]+'.mo'
                check_call(['msgfmt', '-vv', po, '-o', mo])

class BuildScripts(build_scripts):
    def run(self):
        build_scripts.run(self)
        for script in self.scripts:
            script = convert_path(script)
            outfile = join(self.build_dir, basename(script))
            if os.path.exists(outfile) and outfile.endswith(".py"):
                newfile = outfile[:-3] # drop .py
                log.info("renaming %s -> %s", outfile, basename(newfile))
                os.rename(outfile, newfile)

setup(name="redhat-upgrade-tool",
      version="0.7.3",
      description="Red Hat Upgrade",
      long_description="",
      author="Will Woods",
      author_email="wwoods@redhat.com",
      url="https://github.com/dashea/redhat-upgrade-tool",
      download_url="https://github.com/dashea/redhat-upgrade-tool/downloads",
      license="GPLv2+",
      packages=["redhat_upgrade_tool"],
      scripts=["redhat-upgrade-tool.py"],
      cmdclass={
        'gettext': Gettext,
        'msgfmt': Msgfmt,
        'build_scripts': BuildScripts,
        }
      )
