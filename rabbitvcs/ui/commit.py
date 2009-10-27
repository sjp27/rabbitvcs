#
# This is an extension to the Nautilus file manager to allow better 
# integration with the Subversion source control system.
# 
# Copyright (C) 2006-2008 by Jason Field <jason@jasonfield.com>
# Copyright (C) 2007-2008 by Bruce van der Kooij <brucevdkooij@gmail.com>
# Copyright (C) 2008-2008 by Adam Plumb <adamplumb@gmail.com>
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
import thread

import pygtk
import gobject
import gtk

from rabbitvcs.ui import InterfaceView
from rabbitvcs.ui.action import VCSAction
import rabbitvcs.ui.widget
import rabbitvcs.ui.dialog
import rabbitvcs.lib
import rabbitvcs.lib.helper
from rabbitvcs.lib.log import Log
from rabbitvcs.lib.decorators import gtk_unsafe

log = Log("rabbitvcs.ui.commit")

from rabbitvcs import gettext
_ = gettext.gettext

gtk.gdk.threads_init()

class Commit(InterfaceView):
    """
    Provides a user interface for the user to commit working copy
    changes to a repository.  Pass it a list of local paths to commit.
    
    """

    TOGGLE_ALL = False
    SHOW_UNVERSIONED = True

    def __init__(self, paths, base_dir=None):
        """
        
        @type  paths:   list of strings
        @param paths:   A list of local paths.
        
        """
        InterfaceView.__init__(self, "commit", "Commit")

        self.paths = paths
        self.base_dir = base_dir
        self.vcs = rabbitvcs.lib.vcs.create_vcs_instance()
        self.common = rabbitvcs.lib.helper.get_common_directory(paths)
        self.activated_cache = {}

        if not self.vcs.get_versioned_path(self.common):
            rabbitvcs.ui.dialog.MessageBox(_("The given path is not a working copy"))
            raise SystemExit()

        self.files_table = rabbitvcs.ui.widget.Table(
            self.get_widget("files_table"),
            [gobject.TYPE_BOOLEAN, gobject.TYPE_STRING, gobject.TYPE_STRING, 
                gobject.TYPE_STRING, gobject.TYPE_STRING], 
            [rabbitvcs.ui.widget.TOGGLE_BUTTON, _("Path"), _("Extension"), 
                _("Text Status"), _("Property Status")],
            base_dir=base_dir,
            path_entries=[1]
        )
        self.last_row_clicked = None
        
        self.message = rabbitvcs.ui.widget.TextView(
            self.get_widget("message")
        )
        self.get_widget("to").set_text(
            self.vcs.get_repo_url(self.common)
        )

        self.items = None
        self.initialize_items()
        
    #
    # Helper functions
    # 

    @gtk_unsafe
    def load(self):
        """
          - Gets a listing of file items that are valid for the commit window.
          - Determines which items should be "activated" by default
          - Populates the files table with the retrieved items
          - Updates the status area        
        """

        self.get_widget("status").set_text(_("Loading..."))
        self.items = self.vcs.get_items(self.paths, self.vcs.STATUSES_FOR_COMMIT)

        if len(self.activated_cache) == 0:
            for item in self.items:
                self.activated_cache[item.path] = self.should_item_be_activated(item)

        self.populate_files_table()
        self.get_widget("status").set_text(_("Found %d item(s)") % len(self.items))
    
    def get_last_path(self):
        return self.files_table.get_row(self.last_row_clicked)[1]

    def should_item_be_activated(self, item):
        """
        Determines if a file should be activated or not
        """
        
        if (item.path in self.paths
                or item.is_versioned):
            return True

        return False

    def initialize_activated_cache(self):
        """
        Resets and populates the activated cache based on the existing state
        of the files table.
        
        The activated cache is used to "remember" which items are checked off
        before it populates (and possibly changes) the files table entries
        """
        
        self.activated_cache = {}

        for row in self.files_table.get_items():
            self.activated_cache[row[1]] = row[0]

    def populate_files_table(self):
        """
        First clears and then populates the files table based on the items
        retrieved in self.load()
        
        """
        
        self.files_table.clear()

        for item in self.items:
            if item.path in self.activated_cache:
                checked = self.activated_cache[item.path]
            else:
                self.activated_cache[item.path] = self.should_item_be_activated(item)
                checked = self.activated_cache[item.path]
            
            self.files_table.append([
                checked,
                item.path, 
                rabbitvcs.lib.helper.get_file_extension(item.path),
                item.text_status,
                item.prop_status
            ])

    @gtk_unsafe
    def initialize_items(self):
        """
        Initializes the activated cache and loads the file items in a new thread
        """
        
        try:
            self.initialize_activated_cache()
            thread.start_new_thread(self.load, ())
        except Exception, e:
            log.exception(e)

    #
    # Event handlers
    #
    
    def on_destroy(self, widget):
        self.close()
        
    def on_cancel_clicked(self, widget, data=None):
        self.close()
        
    def on_ok_clicked(self, widget, data=None):
        items = self.files_table.get_activated_rows(1)
        self.hide()

        if len(items) == 0:
            self.close()
            return

        added = 0
        for item in items:
            try:
                if self.vcs.status(item, recurse=False)[0].text_status == self.vcs.STATUS["unversioned"]:
                    self.vcs.add(item)
                    added += 1
            except Exception, e:
                print str(e)

        ticks = added + len(items)*2

        self.action = rabbitvcs.ui.action.VCSAction(
            self.vcs,
            register_gtk_quit=self.gtk_quit_is_set()
        )
        self.action.set_pbar_ticks(ticks)
        self.action.append(self.action.set_header, _("Commit"))
        self.action.append(self.action.set_status, _("Running Commit Command..."))
        self.action.append(
            rabbitvcs.lib.helper.save_log_message, 
            self.message.get_text()
        )
        self.action.append(self.vcs.commit, items, self.message.get_text())
        self.action.append(self.action.set_status, _("Completed Commit"))
        self.action.append(self.action.finish)
        self.action.start()
        
    def on_toggle_show_all_toggled(self, widget, data=None):
        self.TOGGLE_ALL = not self.TOGGLE_ALL
        for row in self.files_table.get_items():
            row[0] = self.TOGGLE_ALL
            
    def on_toggle_show_unversioned_toggled(self, widget, data=None):
        self.SHOW_UNVERSIONED = not self.SHOW_UNVERSIONED

        if self.SHOW_UNVERSIONED:
            self.initialize_activated_cache()
            self.populate_files_table()
        else:
            index = 0
            for row in self.files_table.get_items():
                if not self.vcs.is_versioned(row[1]):
                    self.files_table.remove(index)
                    index -= 1
                index += 1
        
    def on_files_table_button_pressed(self, treeview, event):
        pathinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
        if pathinfo is not None:
            path, col, cellx, celly = pathinfo
            treeview.grab_focus()
            treeview.set_cursor(path, col, 0)
            treeview_model = treeview.get_model().get_model()
            fileinfo = treeview_model[path]
            
            if event.button == 3:
                self.last_row_clicked = path
                context_menu = rabbitvcs.ui.widget.ContextMenu([
                    {
                        "label": _("View Diff"),
                        "signals": {
                            "activate": {
                                "callback": self.on_context_diff_activated, 
                                "args": fileinfo
                            }
                        },
                        "condition": self.condition_view_diff
                    },
                    {
                        "label": _("Open"),
                        "signals": {
                            "activate": {
                                "callback": self.on_context_open_activated, 
                                "args": fileinfo
                            }
                        },
                        "condition": self.condition_open
                    },
                    {
                        "label": _("Browse to"),
                        "signals": {
                            "activate": {
                                "callback": self.on_context_browse_activated, 
                                "args": fileinfo
                            }
                        },
                        "condition": (lambda: True)
                    },
                    {
                        "label": _("Delete"),
                        "signals": {
                            "activate": {
                                "callback": self.on_context_delete_activated, 
                                "args": fileinfo
                            }
                        },
                        "condition": self.condition_delete
                    },
                    {
                        "label": _("Add"),
                        "signals": {
                            "activate": {
                                "callback": self.on_context_add_activated, 
                                "args": fileinfo
                            }
                        },
                        "condition": self.condition_add
                    },
                    {
                        "label": _("Revert"),
                        "signals": {
                            "activate": {
                                "callback": self.on_context_revert_activated, 
                                "args": fileinfo
                            }
                        },
                        "condition": self.condition_revert
                    },
                    {
                        "label": _("Restore"),
                        "signals": {
                            "activate": {
                                "callback": self.on_context_restore_activated, 
                                "args": fileinfo
                            }
                        },
                        "condition": self.condition_restore
                    },
                    {
                        "label": _("Add to ignore list"),
                        'submenu': [
                            {
                                "label": os.path.basename(fileinfo[1]),
                                "signals": {
                                    "activate": {
                                        "callback": self.on_subcontext_ignore_by_filename_activated, 
                                        "args": fileinfo
                                     }
                                 },
                                "condition": self.condition_ignore
                            },
                            {
                                "label": "*%s"%fileinfo[2],
                                "signals": {
                                    "activate": {
                                        "callback": self.on_subcontext_ignore_by_fileext_activated, 
                                        "args": fileinfo
                                    }
                                },
                                "condition": self.condition_ignore_by_fileext
                            }
                        ],
                        "condition": self.condition_ignore
                    }
                ])
                context_menu.show(event)

    def on_files_table_row_doubleclicked(self, treeview, event, col):
        treeview.grab_focus()
        treeview.set_cursor(event[0], col, 0)
        treeview_model = treeview.get_model().get_model()
        fileinfo = treeview_model[event[0]]

        rabbitvcs.lib.helper.launch_diff_tool(fileinfo[1])

    def on_context_add_activated(self, widget, data=None):
        self.vcs.add(data[1])
        self.files_table.get_row(self.last_row_clicked)[0] = True
        self.initialize_items()

    def on_context_revert_activated(self, widget, data=None):
        self.vcs.revert(data[1])
        self.initialize_items()

    def on_context_diff_activated(self, widget, data=None):
        rabbitvcs.lib.helper.launch_diff_tool(data[1])

    def on_context_open_activated(self, widget, data=None):
        rabbitvcs.lib.helper.open_item(data[1])
        
    def on_context_browse_activated(self, widget, data=None):
        rabbitvcs.lib.helper.browse_to_item(data[1])

    def on_context_delete_activated(self, widget, data=None):
        if self.vcs.is_versioned(data[1]):
            self.vcs.remove(data[1], force=True)
            self.initialize_items()
        else:
            confirm = rabbitvcs.ui.dialog.DeleteConfirmation(data[1])
            
            if confirm.run():
                rabbitvcs.lib.helper.delete_item(data[1])
                self.files_table.remove(self.last_row_clicked)
            
    def on_subcontext_ignore_by_filename_activated(self, widget, data=None):
        prop_name = self.vcs.PROPERTIES["ignore"]
        prop_value = os.path.basename(data[1])

        if self.vcs.propset(self.base_dir, prop_name, prop_value):
            self.initialize_items()
        
    def on_subcontext_ignore_by_fileext_activated(self, widget, data=None):
        prop_name = self.vcs.PROPERTIES["ignore"]
        prop_value = "*%s" % data[2]
        
        if self.vcs.propset(self.base_dir, prop_name, prop_value, recurse=True):
            self.initialize_items()

    def on_context_restore_activated(self, widget, data=None):
        rabbitvcs.lib.helper.launch_ui_window(
            "update", 
            [data[1]],
            return_immmediately=False
        )
        self.initialize_items()
        
    def on_previous_messages_clicked(self, widget, data=None):
        dialog = rabbitvcs.ui.dialog.PreviousMessages()
        message = dialog.run()
        if message is not None:
            self.message.set_text(message)
    
    # Conditions
    
    def condition_add(self):
        path = self.get_last_path()
        return (
            not self.vcs.is_versioned(path)
        )
    
    def condition_revert(self):
        path = self.get_last_path()
        return (
            self.vcs.is_added(path) or
            self.vcs.is_deleted(path) or
            self.vcs.is_modified(path)
        )

    def condition_view_diff(self):
        path = self.get_last_path()
        return (
            self.vcs.is_modified(path)
        )

    def condition_restore(self):
        path = self.get_last_path()
        return (
            self.vcs.is_missing(path)
        )

    def condition_delete(self):
        path = self.get_last_path()
        return (
            not self.vcs.is_deleted(path)
        )

    def condition_ignore(self):
        path = self.get_last_path()
        if path == self.base_dir:
            return False
        
        return True
    
    def condition_ignore_by_fileext(self):
        return os.path.isfile(self.get_last_path())

    def condition_open(self):
        path = self.files_table.get_row(self.last_row_clicked)[1]
        return os.path.isfile(path)

if __name__ == "__main__":
    from rabbitvcs.ui import main
    (options, paths) = main()

    window = Commit(paths, options.base_dir)
    window.register_gtk_quit()
    gtk.main()
