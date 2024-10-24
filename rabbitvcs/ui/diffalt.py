from __future__ import absolute_import
from rabbitvcs import gettext
from rabbitvcs.util.log import Log
from rabbitvcs.util.strings import S
from rabbitvcs.ui.action import SVNAction, GitAction
import rabbitvcs.vcs
from rabbitvcs.ui import InterfaceView
from rabbitvcs import TEMP_DIR_PREFIX
from gi.repository import Gtk, GObject, Gdk, GLib

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

import os
import six.moves._thread
from time import sleep

from rabbitvcs.util import helper

from gi import require_version
require_version("Gtk", "3.0")
sa = helper.SanitizeArgv()
sa.restore()

from rabbitvcs.util.contextmenu import GtkFilesContextMenu, GtkContextMenuCaller
import rabbitvcs.ui.action
import rabbitvcs.ui.widget
import rabbitvcs.ui.dialog
import rabbitvcs.util
from rabbitvcs.util.strings import S
from rabbitvcs.util.log import Log
from rabbitvcs.util.decorators import gtk_unsafe
import rabbitvcs.vcs.status
from diff import SVNDiff, GitDiff

log = Log("rabbitvcs.ui.diffalt")

from rabbitvcs import gettext
_ = gettext.gettext

helper.gobject_threads_init()

class DiffAlt(InterfaceView, GtkContextMenuCaller):
    """
    Provides a user interface for the user to diff working copy
    changes to a repository.  Pass it a list of local paths to diff.

    """
    SETTINGS = rabbitvcs.util.settings.SettingsManager()

    SHOW_UNVERSIONED = SETTINGS.get("general", "show_unversioned_files")

    # This keeps track of any changes that the user has made to the row
    # selections
    changes = {}

    def __init__(self, paths, base_dir=None):
        """

        @type  paths:   list of strings
        @param paths:   A list of local paths.

        """
        InterfaceView.__init__(self, "diffalt", "DiffAlt")

        self.base_dir = base_dir
        self.vcs = rabbitvcs.vcs.VCS()
        self.items = []

        self.files_table = rabbitvcs.ui.widget.Table(
            self.get_widget("files_table"),
            [rabbitvcs.ui.widget.TYPE_HIDDEN_OBJECT, rabbitvcs.ui.widget.TYPE_HIDDEN_OBJECT,
                rabbitvcs.ui.widget.TYPE_PATH,
                GObject.TYPE_STRING, rabbitvcs.ui.widget.TYPE_STATUS,
                GObject.TYPE_STRING],
            ["", "", _("Path"), _("Extension"),
                _("Text Status"), _("Property Status")],
            filters=[{
                "callback": rabbitvcs.ui.widget.path_filter,
                "user_data": {
                    "base_dir": base_dir,
                    "column": 2
                }
            }],
            callbacks={
                "row-activated":  self.on_files_table_row_activated,
                "mouse-event":   self.on_files_table_mouse_event,
                "key-event":     self.on_files_table_key_event,
                "row-toggled":   self.on_files_table_toggle_event
            },
            flags={
                "sortable": True,
                "sort_on": 2
            }
        )
        self.files_table.allow_multiple()
        self.get_widget("toggle_show_unversioned").set_active(self.SHOW_UNVERSIONED)

        self.paths = []
        for path in paths:
            if self.vcs.is_in_a_or_a_working_copy(path):
                self.paths.append(S(path))

    #
    # Helper functions
    #

    def load(self):
        """
          - Gets a listing of file items that are valid for the commit window.
          - Determines which items should be "activated" by default
          - Populates the files table with the retrieved items
          - Updates the status area
        """

        self.get_widget("status").set_text(_("Loading..."))

        self.items = self.vcs.get_items(self.paths, self.vcs.statuses_for_commit(self.paths))

        self.populate_files_table()

    # Overrides the GtkContextMenuCaller method
    def on_context_menu_command_finished(self):
        self.initialize_items()

    def should_item_be_activated(self, item):
        """
        Determines if a file should be activated or not
        """

        if (S(item.path) in self.paths
                or item.is_versioned()
                and item.simple_content_status() != rabbitvcs.vcs.status.status_missing):
            return True

        return False

    def should_item_be_visible(self, item):
        show_unversioned = self.SHOW_UNVERSIONED

        if not show_unversioned:
            if not item.is_versioned():
               return False

        return True

    def initialize_items(self):
        """
        Initializes the activated cache and loads the file items in a new thread
        """

        GLib.idle_add(self.load)

    def show_files_table_popup_menu(self, treeview, data):
        paths = self.files_table.get_selected_row_items(1)
        GtkFilesContextMenu(self, data, self.base_dir, paths).show()

    def delete_items(self, widget, event):
        paths = self.files_table.get_selected_row_items(1)
        if len(paths) > 0:
            proc = helper.launch_ui_window("delete", paths)
            self.rescan_after_process_exit(proc, paths)

    #
    # Event handlers
    #
    def on_refresh_clicked(self, widget):
        self.initialize_items()

    def on_key_pressed(self, widget, event, *args):
        if InterfaceView.on_key_pressed(self, widget, event, *args):
            return True

        if (event.state & Gdk.ModifierType.CONTROL_MASK and
                Gdk.keyval_name(event.keyval) == "Return"):
            self.on_ok_clicked(widget)
            return True

    def on_toggle_show_unversioned_toggled(self, widget, *args):
        self.SHOW_UNVERSIONED = widget.get_active()
        self.populate_files_table()

        # Save this preference for future diffalt.
        if self.SETTINGS.get("general", "show_unversioned_files") != self.SHOW_UNVERSIONED:
            self.SETTINGS.set(
                "general", "show_unversioned_files",
                self.SHOW_UNVERSIONED
            )
            self.SETTINGS.write()

    def on_files_table_row_activated(self, treeview, event, col):
        paths = self.files_table.get_selected_row_items(1)
        pathrev1 = helper.create_path_revision_string(paths[0], "base")
        pathrev2 = helper.create_path_revision_string(paths[0], "working")
        proc = helper.launch_ui_window("diff", ["-s", pathrev1, pathrev2])
        self.rescan_after_process_exit(proc, paths)

    def on_files_table_key_event(self, treeview, event, *args):
        if Gdk.keyval_name(event.keyval) == "Delete":
            self.delete_items(treeview, event)

    def on_files_table_mouse_event(self, treeview, event, *args):
        if event.button == 3 and event.type == Gdk.EventType.BUTTON_RELEASE:
            self.show_files_table_popup_menu(treeview, event)

    def populate_files_table(self):
        """
        First clears and then populates the files table based on the items
        retrieved in self.load()

        """

        self.files_table.clear()
        n = 0
        m = 0
        for item in self.items:
            if item.path in self.changes:
                checked = self.changes[item.path]
            else:
                checked = self.should_item_be_activated(item)
            checked = False;

            if item.is_versioned():
                n += 1
            else:
                m += 1

            if not self.should_item_be_visible(item):
                continue

            self.files_table.append([
                checked,
                S(item.path),
                item.path,
                helper.get_file_extension(item.path),
                item.simple_content_status(),
                item.simple_metadata_status()
            ])
        self.get_widget("status").set_text(_("Found %(changed)d changed and %(unversioned)d unversioned item(s)") % {
                "changed": n,
                "unversioned": m
            }
        )

class SVNDiffAlt(DiffAlt):
    def __init__(self, paths, base_dir=None):
        DiffAlt.__init__(self, paths, base_dir)

        self.get_widget("commit_to_box").show()

        self.get_widget("to").set_text(
            S(self.vcs.svn().get_repo_url(self.base_dir)).display()
        )

        self.items = None
        if len(self.paths):
            self.initialize_items()

    def on_files_table_toggle_event(self, row, col):
        # Adds path: True/False to the dict
        self.changes[row[1]] = row[col]

class GitDiffAlt(DiffAlt):
    def __init__(self, paths, base_dir=None):
        DiffAlt.__init__(self, paths, base_dir)

        self.git = self.vcs.git(paths[0])

        self.get_widget("commit_to_box").show()

        active_branch = self.git.get_active_branch()
        if active_branch:
            self.get_widget("to").set_text(
                S(active_branch.name).display()
            )
        else:
            self.get_widget("to").set_text("No active branch")

        self.items = None
        if len(self.paths):
            self.initialize_items()

    def on_files_table_toggle_event(self, row, col):
        # Adds path: True/False to the dict
        self.changes[row[1]] = row[col]

classes_map = {
    rabbitvcs.vcs.VCS_SVN: SVNDiffAlt,
    rabbitvcs.vcs.VCS_GIT: GitDiffAlt
}

classes_map_file = {
    rabbitvcs.vcs.VCS_SVN: SVNDiff,
    rabbitvcs.vcs.VCS_GIT: GitDiff
}

def diffalt_factory(paths, base_dir=None):
    guess = rabbitvcs.vcs.guess(paths[0])
    vcs = guess["vcs"]

    if len(paths) == 1 and os.path.isfile(paths[0]):  
        return classes_map_file[vcs](paths[0], None, None, None, True)
    else:
        return classes_map[guess["vcs"]](paths, base_dir)

if __name__ == "__main__":
    from rabbitvcs.ui import main, BASEDIR_OPT
    (options, paths) = main(
        [BASEDIR_OPT],
        usage="Usage: rabbitvcs diffalt [path1] [path2] ...",
    )

    window = diffalt_factory(paths, options.base_dir)
    window.register_gtk_quit()
    Gtk.main()
