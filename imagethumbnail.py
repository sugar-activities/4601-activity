#!/usr/bin/env python
# -*- coding: utf-8 -*-

# ImageThumbnail.py
# Copyright (C) 2010 OLPC
# Incorporates journal viewer from SugarCommander.activity by James D. Simmons
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os
import sys
import logging
import zipfile
import time
import traceback
from subprocess import Popen, PIPE

import gi
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Pango
from gi.repository import GdkPixbuf
from gi.repository import Gio

from sugar3 import mime
from sugar3.activity import activity
from sugar3.datastore import datastore
from sugar3.graphics import style
from sugar3.graphics.toolbarbox import ToolbarBox
from sugar3.activity.widgets import ActivityButton
from sugar3.activity.widgets import TitleEntry
from sugar3.activity.widgets import StopButton

from gettext import gettext as _

COLUMN_TITLE = 0
COLUMN_JOBJECT = 3
COLUMN_IMAGE = 0
COLUMN_PATH = 1
COLUMN_MTIME = 2
max_file = 1000

_logger = logging.getLogger('image-thumbnail')

def get_mounts():
    
    volume_monitor = Gio.VolumeMonitor.get()
    
    mounts = []
    for mount in volume_monitor.get_mounts():
        description = {}
        description['mount_path'] = mount.get_default_location().get_path()
        description['label'] = mount.get_name()
        mounts.append(description)
        
    return mounts

class ImageThumbnail(activity.Activity):
    """The entry point to the Activity"""
    
    def __init__(self, handle, create_jobject = True):
        
        activity.Activity.__init__(self, handle)
        
        self.selected_journal_entry = None
        self.selected_path = None
        
        self.canvas = Gtk.Notebook()
        self.canvas.props.show_border = True
        self.canvas.props.show_tabs = True
        self.canvas.show()
        
        self.last_col = 0
        cols = 3
        ds_mounts = get_mounts()
        # check if externmal media used in journal
        if ds_mounts: cols = 4
        
        self.ls_journal = []
        self.tv_journal = []
        self.col_journal = []
        self.column_table = []
        self.scroll = []
        self.vbox = []
        self.hidden = []
        self.image = [[],[],[],[],[]]
        self.btn_delete = [[],[],[],[],[]]
        self.btn_show = [[],[],[],[],[]]
        self.title_entry = [[],[],[],[],[]]
        self.tab_label = []
        
        for col in range(cols):

            self.ls_journal.append(
                Gtk.ListStore(GObject.TYPE_STRING,
                GObject.TYPE_UINT64,
                GObject.TYPE_STRING,
                GObject.TYPE_PYOBJECT))
                
            self.tv_journal.append( Gtk.TreeView(self.ls_journal[col]))
            self.tv_journal[col].set_rules_hint(True)
            self.tv_journal[col].set_search_column(COLUMN_TITLE)
            
            renderer = Gtk.CellRendererText()
            renderer.set_property('wrap-mode', Gtk.WrapMode.WORD)
            renderer.set_property('wrap-width', 500)
            renderer.set_property('width', 500)
            
            self.col_journal.append(Gtk.TreeViewColumn(_('Title'),
                renderer, text = COLUMN_TITLE))
            self.col_journal[col].set_sort_column_id(COLUMN_MTIME)
            self.tv_journal[col].append_column(self.col_journal[col])
        
            # FIXME: have to change everything about pango
            # label_attributes = Pango.AttrList()
            # label_attributes.insert(Pango.AttrSize(14000, 0, -1))
            # label_attributes.insert(Pango.AttrForeground(65535, 65535, 65535, 0, -1))
            
            if col == 0:
                self.tab_label.append(Gtk.Label(_("Journal")))
                
            elif col == 1:
                self.tab_label.append(Gtk.Label(_("Files")))
                
            elif (cols == 4 and col == 2):
                self.tab_label.append(Gtk.Label(_("External")))
                
            else:
                self.tab_label.append(Gtk.Label(_("Read Only")))
            
            # FIXME: have to change everything about pango
            #self.tab_label[col].set_attributes(label_attributes)
            #self.tab_label[col].show()
            #self.tv_journal[col].show()
            if col == 0: self.load_journal_table(col)
            else: self.load_file_table(col)
            
            num = self.ls_journal[col].iter_n_children(None)
            
            if num == 0:
                #dummy elements for no external files
                self.column_table.append( Gtk.Table(1, 1, homogeneous = False))
                self.scroll.append(Gtk.ScrolledWindow(hadjustment = None,
                    vadjustment = None))
                self.vbox.append(Gtk.VBox(homogeneous = True, spacing=5))
                self.canvas.append_page(self.vbox[col],self.tab_label[col])
                self.tab_label[col].hide()
                self.vbox[col].hide()
                self.hidden.append(col)
                
            else:
                self.tab_label[col].show()
                self.tv_journal[col].show()
            
            self.column_table.append( Gtk.Table(rows = num,
                columns = 3, homogeneous = False))
            self.scroll.append(Gtk.ScrolledWindow(hadjustment = None,
                vadjustment = None))
            self.scroll[col].set_policy(Gtk.PolicyType.AUTOMATIC,
                Gtk.PolicyType.AUTOMATIC)
            
            iter = self.ls_journal[col].get_iter_first()
            n=0
            
            while(iter != None):
                tv = self.tv_journal[col]
                model = tv.get_model()
                
                jobject = model.get_value(iter,COLUMN_JOBJECT)
                
                i = n - (3 * int(n / 3))
                j = 2 * int( n / 3)
                image_table = Gtk.Table(rows = 2, columns = 2, homogeneous = False)
                
                self.image[col].append( Gtk.Image())
                image_table.attach(self.image[col][n], 0, 2, 0, 1,
                    xoptions = Gtk.AttachOptions.FILL |
                    Gtk.AttachOptions.SHRINK,
                    yoptions = Gtk.AttachOptions.FILL |
                    Gtk.AttachOptions.SHRINK,
                    xpadding = 5, ypadding = 5)
                    
                self.btn_show[col].append(Gtk.Button(_("Show File")))
                self.btn_show[col][n].connect('button_press_event',
                    self.show_button_press_event_cb, col,n)
                    
                image_table.attach(self.btn_show[col][n], 0, 1, 1, 2,
                    xoptions = Gtk.AttachOptions.SHRINK,
                    yoptions = Gtk.AttachOptions.SHRINK,
                    xpadding = 5, ypadding = 5)
                self.btn_show[col][n].show()
                
                if col < cols - 1:
                    self.btn_delete[col].append(Gtk.Button(_("Delete")))
                    self.btn_delete[col][n].connect('button_press_event',
                        self.delete_button_press_event_cb, col,n)
                        
                    image_table.attach(self.btn_delete[col][n], 1, 2, 1, 2,
                        xoptions = Gtk.AttachOptions.SHRINK,
                        yoptions = Gtk.AttachOptions.SHRINK,
                        xpadding = 5, ypadding = 5)
                    self.btn_delete[col][n].show()
                    self.btn_delete[col][n].props.sensitive = True
                    
                image_table.show()
                
                self.column_table[col].attach(image_table, i, i+1, j+1, j+2,
                    xoptions = Gtk.AttachOptions.FILL |
                    Gtk.AttachOptions.EXPAND |
                    Gtk.AttachOptions.SHRINK,
                    yoptions = Gtk.AttachOptions.FILL |
                    Gtk.AttachOptions.EXPAND |
                    Gtk.AttachOptions.SHRINK,
                    xpadding = 5, ypadding = 5)
                    
                self.set_form_fields(jobject,col,n)
                self.btn_show[col][n].props.sensitive = True
                
                iter=self.ls_journal[col].iter_next(iter)
                n+=1
                
            self.scroll[col].add_with_viewport(self.column_table[col])
            self.scroll[col].set_events(Gdk.EventMask.POINTER_MOTION_MASK)
            self.scroll[col].show()
            self.vbox.append(Gtk.VBox(homogeneous=True, spacing=5))
            self.vbox[col].pack_start(self.scroll[col], True, True, 0)
            self.canvas.append_page(self.vbox[col], self.tab_label[col])
            
        self.tab_label.append(Gtk.Label(_("File Viewer")))
        # FIXME: have to change everything about pango
        #self.tab_label[cols].set_attributes(label_attributes)
        self.tab_label[cols].show()
        self.vbox_view=self.draw_metatable(cols)
        self.canvas.append_page(self.vbox_view, self.tab_label[cols])

        self.set_canvas(self.canvas)
        self.show_all()
        self.vbox_view.hide()
        self.tab_label[cols].hide()
        
        toolbar_box = ToolbarBox()
        self.set_toolbar_box(toolbar_box)
        toolbar_box.toolbar.insert(TitleEntry(self), -1)
        separator = Gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        toolbar_box.toolbar.insert(separator, -1)

        toolbar_box.toolbar.insert(StopButton(self), -1)
        toolbar_box.show_all()
        
        for n in self.hidden:
            self.tab_label[n].hide()
            self.vbox[n].hide()
    #can use in future to load in background

    def motion_notify_event(self,widget,event,col):
        
        self.tv_journal[col].show()
        self.scroll[col]= Gtk.ScrolledWindow(
            hadjustment=None, vadjustment=None)
        self.scroll[col].set_policy(Gtk.PolicyType.AUTOMATIC,
            Gtk.PolicyType.AUTOMATIC)
        self.menu_file()
        self.scroll[col].show()
        self.vbox[col] = Gtk.VBox(homogeneous=True, spacing=5)
        self.vbox[col].pack_start(self.scroll[col], True, True, 0)
        
        widget.append_page(sef.vbox[col], self.tab_label[col])
        widget.show()
        #reload

    def remove_image(self, col,id):
        
        iter = self.ls_journal[col].get_iter_first()
        n = 0
        tv = self.tv_journal[col]
        model = tv.get_model()
        self.image[col][id].hide()
        
    def draw_metatable(self, col):
        
        self._secondary_view = Gtk.VBox()
        self.detail_view = Gtk.Table(5,5, homogeneous= False)
        go_back = Gtk.Button(_("back"))
        go_back.connect('button_press_event',
            self._go_back_clicked_cb, col)
        go_back.show()
        
        self.detail_view.attach(go_back, 0, 1, 0, 1,
            xoptions = Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            yoptions = Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            xpadding = 5, ypadding = 5)
        
        #image
        self.large_image = Gtk.Image()
        self.detail_view.attach(self.large_image, 0, 3, 1, 5,
            xoptions = Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            yoptions = Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            xpadding = 5, ypadding = 5)
            
        self.detail_view.attach(self.large_image,0,3,1,5)
        
        self.large_image.show()
        
        #filename
        title_label = Gtk.Label(_("Title"))
        
        self.detail_view.attach(title_label, 3, 4, 0, 1,
            xoptions = Gtk.AttachOptions.SHRINK,
            yoptions = Gtk.AttachOptions.SHRINK,
            xpadding = 10, ypadding = 10)
            
        title_label.show()
        
        self.title_textview = Gtk.TextView()
        self.title_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        
        self.detail_view.attach(self.title_textview, 4, 5, 0, 1,
            xoptions = Gtk.AttachOptions.EXPAND |
            Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            yoptions = Gtk.AttachOptions.EXPAND |
            Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            xpadding = 10, ypadding = 10)
            
        self.title_textview.props.accepts_tab = False
        self.title_textview.show()
        
        #filepath
        description_label = Gtk.Label(_("Description"))
        
        self.detail_view.attach(description_label, 3, 4, 1, 2,
            xoptions = Gtk.AttachOptions.SHRINK,
            yoptions = Gtk.AttachOptions.SHRINK,
            xpadding = 10, ypadding = 10)
            
        description_label.show()
        
        self.description_textview = Gtk.TextView()
        self.description_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        
        self.detail_view.attach(self.description_textview, 4, 5, 1, 2,
            xoptions = Gtk.AttachOptions.EXPAND |
            Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            yoptions = Gtk.AttachOptions.EXPAND |
            Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            xpadding = 10, ypadding = 10)
            
        self.description_textview.props.accepts_tab = False
        self.description_textview.show()
        
        #mtime
        mtime_label = Gtk.Label(_("Created"))
        
        self.detail_view.attach(mtime_label, 3, 4, 2,3,
            xoptions = Gtk.AttachOptions.SHRINK,
            yoptions = Gtk.AttachOptions.SHRINK,
            xpadding = 10, ypadding = 10)
            
        mtime_label.show()
        
        self.mtime_textview = Gtk.TextView()
        self.mtime_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        
        self.detail_view.attach(self.mtime_textview, 4, 5, 2,3,
            xoptions = Gtk.AttachOptions.EXPAND |
            Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            yoptions = Gtk.AttachOptions.EXPAND |
            Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            xpadding = 10, ypadding = 10)
            
        self.mtime_textview.props.accepts_tab = False
        self.mtime_textview.show()
        
        #mime_type
        mime_label= Gtk.Label(_("Type"))
        
        self.detail_view.attach(mime_label, 3, 4, 3,4,
            xoptions = Gtk.AttachOptions.SHRINK,
            yoptions = Gtk.AttachOptions.SHRINK,
            xpadding = 10, ypadding = 10)
            
        mime_label.show()
        
        self.mime_textview = Gtk.TextView()
        self.mime_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        
        self.detail_view.attach(self.mime_textview, 4, 5, 3,4,
            xoptions = Gtk.AttachOptions.EXPAND |
            Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            yoptions = Gtk.AttachOptions.EXPAND |
            Gtk.AttachOptions.FILL |
            Gtk.AttachOptions.SHRINK,
            xpadding = 10, ypadding = 10)
            
        self.mime_textview.props.accepts_tab = False
        self.mime_textview.show()
        
        self._secondary_view.pack_end(self.detail_view, True, True, 0)
        self.detail_view.show()
        return self._secondary_view

    def show_button_press_event_cb(self, entry, event, col,row):
        
        # Need to get the full set of properties
        iter = self.ls_journal[col].get_iter_first()
        n = 0
        tv = self.tv_journal[col]
        model = tv.get_model()
        
        while(iter != None and n < (row)):
            iter = self.ls_journal[col].iter_next(iter)
            n += 1
            jobject = model.get_value(iter,COLUMN_JOBJECT)
            
            object_id = jobject.get_object_id()
            metadata = jobject.get_file_metadata()
        
            try:
                scaled_buf = self.show_image(jobject.get_file_path())
                self.large_image.set_from_pixbuf(scaled_buf)
            except Exception:
                logging.error('Exception while displaying entry:\n' + \
                ''.join(traceback.format_exception(*sys.exc_info())))
            
            title_textbuf = self.title_textview.get_buffer()
            if metadata['title'] != None: title_textbuf.set_text(metadata['title'])
            desc_textbuf = self.description_textview.get_buffer()
            
            if metadata['description']!=None:
                desc_textbuf.set_text(metadata['description'])
                
            mime_textbuf = self.mime_textview.get_buffer()
            mime_textbuf.set_text(metadata['mime_type'])
            mtime_textbuf = self.mtime_textview.get_buffer()
            #time from curent
            mtime=time.asctime(time.localtime(float(metadata['timestamp'])))
            mtime_textbuf.set_text(str(mtime))
            
        self._secondary_view.show()
        self.vbox_view.show()
        self.canvas.set_current_page(len(self.vbox))
        self.last_col = col

    def _go_back_clicked_cb(self,entry,event,col):
        
        self.tab_label[col].hide()
        self.vbox_view.hide()
        self.canvas.set_current_page(self.last_col)
        
    def delete_button_press_event_cb(self, entry, event, col,id):
        
        i = 0
        tv = self.tv_journal[col]
        model = tv.get_model()
        iter = self.ls_journal[col].get_iter_first()
        
        while(i < id):
            iter = self.ls_journal[col].iter_next(iter)
            i += 1
            
        if not iter == None:
            jobject = model.get_value(iter,COLUMN_JOBJECT)
            self.ls_journal[col].remove(iter)
            
            if col == 0:
                datastore.delete(jobject.get_object_id())
                
            else:
                try:
                    os.remove(jobject.get_file_path())
                    print 'Deleted %s' % (jobject.get_file_path())
                except OSError: print 'Cannot delete %s' % (jobject.get_file_path())
                
            self.remove_image(col,id)
            self.tv_journal[col].grab_focus()
            self.last_col = col
            
    def close(self,  skip_save = False):
        "Override the close method so we don't try to create a Journal entry."
        
        activity.Activity.close(self, True)
        
    def set_form_fields(self, jobject, col = 0, id = 0):
        #no title
        #self.title_entry[col][id].set_text(jobject.get_title())
        if col == 0:
            self.create_preview(jobject.get_object_id(), col, id)
        else:
            filename = jobject.get_file_path()
            self.show_image(filename, col, id)
            
    def create_preview(self, object_id, col, id):
        
        jobject = datastore.get(object_id)
        
        if jobject.metadata.has_key('preview'):
            preview = jobject.metadata['preview']
            if preview is None or preview == '' or preview == 'None':
                if (jobject.metadata['mime_type'].startswith('image/')):
                    # or (jobject.metadata['mime_type'].startswith('video')):
                    filename = jobject.get_file_path()
                    self.show_image(filename,col,id)
                    return
                
        if jobject.metadata.has_key('preview') and \
            len(jobject.metadata['preview']) > 4:
            
            if jobject.metadata['preview'][1:4] == 'PNG':
                preview_data = jobject.metadata['preview']
            else:
                import base64
                preview_data = base64.b64decode(jobject.metadata['preview'])
                
            loader = Gdk.PixbufLoader()
            loader.write(preview_data)
            scaled_buf = loader.get_pixbuf()
            loader.close()
            self.image[col][id].set_from_pixbuf(scaled_buf)
            self.image[col][id].show()
        else:
            self.image[col][id].clear()
            self.image[col][id].show()
            
    def load_file_table(self,col):
        
        self.num = 0
        if col == 2:
            ds_mounts = get_mounts()
            
            if ds_mounts:
                for mount in ds_mounts:
                    self.load_files(mount['mount_path'], col)
            else:
                self.tab_label[col].hide()
                
        elif col == 1:
            self.load_files('/home/olpc',col)
            
        else:
            f = open('olpc.files','r')
            for line in f:
                line = line.strip()
                self.load_files(os.path.join('/home/olpc', line), col)
                if self.num > max_file: break
            f.close()
        # FIXME: object has no attribute SORT_DESCENDING
        #self.ls_journal[col].set_sort_column_id(COLUMN_MTIME,  Gtk.SORT_DESCENDING)
        
    def load_files(self, dir, col):
        
        for path, dirnames, filenames in os.walk(dir, True):

            if dir == '/home/olpc' :
                f = open('olpc.files','r')
                for line in f:
                    line = line.strip()
                    if line in dirnames:
                        dirnames.remove(line)
                f.close()
                
            else:
                f = open('media.files','r')
                for line in f:
                    line = line.strip()
                    if line in dirnames:
                        dirnames.remove(line)
                f.close()
                
            for filename in filenames:
                file_name = os.path.join(path, filename)
                #remove hidden file_nameexcept for readonly
                pos = str.find(file_name, '/.')
                if col == 3: pos = -1
                name = str.find(file_name, 'Cache')
                
                if ((pos == -1) or name > 0) and not( os.path.islink(file_name)):
                    if self.num > max_file: return
                    try:
                        file_mimetype = mime.get_for_file(os.path.join(path,filename))
                        if (file_mimetype.startswith('image/')) :
                            #or (file_mimetype.startswith('video/')):
                            #check for new files
                            self.num += 1
                            mtime = os.path.getmtime(file_name)
                            iter = self.ls_journal[col].append()
                            jobject_wrapper = JobjectWrapper()
                            jobject_wrapper.set_file_path(os.path.join(path, filename))
                            jobject_wrapper.set_object_id(file_name)
                            jobject_wrapper.set_title(filename)
                            jobject_wrapper.set_mime_type(file_mimetype)
                            jobject_wrapper.set_timestamp(mtime)
                            jobject_wrapper.set_description(file_name)
                            self.ls_journal[col].set(iter, COLUMN_TITLE, filename)
                            self.ls_journal[col].set(iter, COLUMN_MTIME, str(mtime))
                            self.ls_journal[col].set(iter, COLUMN_JOBJECT, jobject_wrapper)
                    except IOError: print 'No mimetype for : %s' % (file_name)
                    
    def load_journal_table(self, col):
        
        ds_mounts = get_mounts()
        mountpoint_id = None
        
        query = {}
        if mountpoint_id is not None:
            query['mountpoints'] = [ mountpoint_id ]
            ds_objects, num_objects = datastore.find(query, properties = ['uid','timestamp',
            'title', 'mime_type', 'description'], sorting = '-timestamp')
            
            self.ls_journal[col].clear()
            for i in xrange (0, num_objects, 1):
                mime = ds_objects[i].metadata['mime_type']
            
                if mime.startswith('image/') or	mime.startswith('video/') :
                    iter = self.ls_journal[col].append()
                    title = ds_objects[i].metadata['title']
                    self.ls_journal[col].set(iter, COLUMN_TITLE, title)
                    jobject_wrapper = JobjectWrapper()
                    jobject_wrapper.set_jobject(ds_objects[i])
                    jobject_wrapper.set_mime_type(mime)
                    mtime = ds_objects[i].metadata.get('timestamp')
                    jobject_wrapper.set_timestamp(mtime)
                    desc = ds_objects[i].metadata.get('description')
                    jobject_wrapper.set_description(desc)
                    title = ds_objects[i].metadata.get('uid')
                    jobject_wrapper.set_title(title)
                    self.ls_journal[col].set(iter, COLUMN_MTIME, mtime)
                    self.ls_journal[col].set(iter, COLUMN_JOBJECT, jobject_wrapper)
                    size = self.get_size(ds_objects[i]) / 1024
        # FIXME: object has no attribute SORT_DESCENDING
        #self.ls_journal[col].set_sort_column_id(COLUMN_MTIME,  Gtk.SORT_DESCENDING)
        
    def get_size(self, jobject):
        """Return the file size for a Journal object."""
        
        logging.debug('get_file_size %r', jobject.object_id)
        path = jobject.get_file_path()
        
        if not path:
            return 0
        
        return os.stat(path).st_size
    
    def show_image(self, filename, col = -1, id = 0):
        """display a resized image in a preview"""
        
        try:
            if filename == None:return
            if col == -1:
                scaled_buf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename,
                    style.zoom(930), style.zoom(700))
                return scaled_buf
            else:
                scaled_buf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename,
                    style.zoom(320), style.zoom(240))
                self.image[col][id].set_from_pixbuf(scaled_buf)
                self.image[col][id].show()
        except IOError: print 'Failed to open image %s' % (filename)
        #except GError: print 'Failed zoom image %s' % (filename)
        
class JobjectWrapper():
    
    def __init__(self):
        
        self.__jobject = None
        self.__file_path = None

    def set_jobject(self, jobject):
        
        self.__jobject = jobject

    def set_file_path(self, file_path):
        
        self.__file_path = file_path

    def set_title(self, filename):
        
        if  self.__jobject != None:
            self.__jobject.metadata['title'] = filename
        else:
            self.__title = filename

    def get_title(self):
        
        if  self.__jobject != None:
            return self.__jobject.metadata['title']
        else:
            return self.__title
        
    def set_mime_type(self,mime_type):
        
        if  self.__jobject != None:
            self.__jobject.metadata['mime_type'] = mime_type
        else:
            self.__mime_type = mime_type
            
    def set_timestamp(self, time):
        
        if  self.__jobject != None:
            self.__jobject.metadata['timestamp'] = time
        else:
            self.__timestamp = time

    def set_description(self, desc):
        
        if  self.__jobject != None:
            self.__jobject.metadata['description'] = desc
        else:
            self.__description = desc

    def set_object_id(self,id):
        
        self.__object_id=id

    def get_file_path(self):
        
        if  self.__jobject != None:
            return self.__jobject.get_file_path()
        else:
            return self.__file_path
        
    def get_timestamp(self):
        
        if self.__jobject != None:
            # may cause error
            return self.__jobject.metadata.get('timestamp')
        else:
            return self.__timestamp
        
    def get_file_metadata(self):
        
        if self.__jobject != None:
            # may cause error
            return self.__jobject.metadata
        else:
            #client = gconf.client_get_default()
            path = self.__file_path
            return {
                'uid': self.__object_id,
                'title': self.__title,
                'timestamp': self.__timestamp,
                'mime_type': self.__mime_type,
                'activity': '',
                'activity_id': '',
                'icon-color': '',
                'description': self.__description
                }
                
    def get_mime_type(self):
        
        if self.__jobject != None:
            return self.__jobject.metadata['mimetype']
        else:
            return self.__mime_type

    def get_object_id(self):
        
        if self.__jobject != None:
            return self.__jobject.object_id
        else:
            return self.__object_id
        