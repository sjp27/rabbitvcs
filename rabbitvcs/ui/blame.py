from __future__ import absolute_import
#
# This is an extension to the Nautilus file manager to allow better
# integration with the Subversion source control system.
#
# Copyright (C) 2006-2008 by Jason Field <jason@jasonfield.com>
# Copyright (C) 2007-2008 by Bruce van der Kooij <brucevdkooij@gmail.com>
# Copyright (C) 2008-2010 by Adam Plumb <adamplumb@gmail.com>
#
# RabbitVCS is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# RabbitVCS is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with RabbitVCS;  If not, see <http://www.gnu.org/licenses/>.
#

import rabbitvcs.ui.action
from rabbitvcs.util.log import Log

import rabbitvcs.vcs

log = Log("rabbitvcs.ui.blame")

from rabbitvcs import gettext
_ = gettext.gettext

class GitBlame(object):
    def __init__(self, path, line):
        self.vcs = rabbitvcs.vcs.VCS()
        self.git = self.vcs.git(path)
        self.action = rabbitvcs.ui.action.GitAction(
            self.git,
            run_in_thread=False
        )
        self.action.append(self.git.blame, [path], line)
        self.action.schedule()

def blame_factory(vcs, path=None, line=0):
    if not vcs:
        guess = rabbitvcs.vcs.guess(path)
        vcs = guess["vcs"]

    return GitBlame(path, line)

if __name__ == "__main__":
    from rabbitvcs.ui import main, VCS_OPT
    (options, args) = main(
        [VCS_OPT],
        usage="Usage: rabbitvcs blame [path] [line]"
    )

    # If two arguments are passed:
    #   The first argument is expected to be a path
    #   The second argument is expected to be a line number
    # If one argument is passed:
    #   If it is a path
    path = None
    line = 0
    if len(args) == 2:
        path = args[0]
        line = args[1]
    elif len(args) == 1:
        path = args[0]

    window = blame_factory(options.vcs, path=path, line=line)

