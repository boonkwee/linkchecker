#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
# Copyright (C) 2004 Sandino Flores Moreno

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA
#
# Changes by Bastian Kleineidam:
#
# - Added command line options (see usage() function)
# - Regenerate helper module if this code generator was modified
# - Use sys.executable as interpreter name
# - Add global root widget map

"""
A code generator that uses pygtk, glade and SimpleGladeApp.py.
"""

import sys
import os
import re
import codecs
import tokenize
import locale
import getopt
import datetime
import shutil
import time
import xml.sax
from xml.sax._exceptions import SAXParseException

# default config
config = {
    "charset": locale.getpreferredencoding(),
    "copyright": u"Copyright (C) %d" % datetime.date.today().year,
    "license": u"",
    "threads": u"pass",
    "interpreter": unicode(sys.executable)
}

def read_config (args):
    preferred_encoding = config["charset"]
    longopts = ["threads", "charset=", "copyright=", "license="]
    opts, args = getopt.getopt(args, "", longopts)
    for opt, arg in opts:
        if opt == "--threads":
            config["threads"] = u"gtk.gdk.threads_init()"
        elif opt == "--copyright":
            config["copyright"] = arg.decode(preferred_encoding)
        elif opt == "--charset":
            charset = arg.decode(preferred_encoding)
            try:
                codecs.lookup(charset)
            except LookupError:
                raise getopt.GetoptError("Unknown charset %r" % arg)
            config["charset"] = charset
        elif opt == "--license":
            fo = codecs.open(arg, "r", preferred_encoding)
            try:
                content = fo.read()
            finally:
                fo.close()
            config["license"] = content
    return args


header_format = u"""\
#!%(interpreter)s
# -*- coding: %(charset)s -*-
# %(copyright)s
%(license)s

# Python module %(module)s.py
# Autogenerated from %(glade)s
# Generated on %(date)s

# Warning: Do not delete or modify comments related to context
# They are required to keep user's code

import os
import gtk
import SimpleGladeApp

glade_dir = ""
root_widgets = {}

# Put your modules and data here

# From here through main() codegen inserts/updates a class for
# every top-level widget in the .glade file.

"""

class_format = u"""\
class %(class)s (SimpleGladeApp.SimpleGladeApp):

%(t)sdef __init__ (self, glade_path="%(glade)s", root="%(root)s", domain=None):
%(t)s%(t)sglade_path = os.path.join(glade_dir, glade_path)
%(t)s%(t)ssuper(%(class)s, self).__init__(glade_path, root, domain)

%(t)sdef new (self):
%(t)s%(t)s#context %(class)s.new {
%(t)s%(t)sprint "A new %(class)s has been created"
%(t)s%(t)s#context %(class)s.new }

%(t)s#context %(class)s custom methods {
%(t)s#--- Write your own methods here ---#
%(t)s#context %(class)s custom methods }

"""

callback_format = u"""\
%(t)sdef %(handler)s (self, widget, *args):
%(t)s%(t)s#context %(class)s.%(handler)s {
%(t)s%(t)sprint "%(handler)s called with self.%%s" %% widget.get_name()
%(t)s%(t)s#context %(class)s.%(handler)s }

"""

creation_format = u"""\
%(t)sdef %(handler)s (self, str1, str2, int1, int2):
%(t)s%(t)s#context %(class)s.%(handler)s {
%(t)s%(t)swidget = gtk.Label("%(handler)s")
%(t)s%(t)swidget.show_all()
%(t)s%(t)sreturn widget
%(t)s%(t)s#context %(class)s.%(handler)s }

"""

main_format = u"""\
def main ():
"""

instance_format = u"""\
%(t)sroot_widgets[%(root)r] = %(class)s()
"""
run_format = u"""\

%(t)s%(root)s.run()

if __name__ == "__main__":
%(t)smain()
"""

class NotGladeDocumentException (SAXParseException):

    def __init__ (self, glade_writer):
        strerror = "Not a glade-2 document"
        SAXParseException.__init__(self, strerror, None, glade_writer.sax_parser)


class SimpleGladeCodeWriter (xml.sax.handler.ContentHandler):

    def __init__ (self, glade_file):
        self.indent = "    "
        self.code = ""
        self.roots_list = []
        self.widgets_stack = []
        self.creation_functions = []
        self.callbacks = []
        self.parent_is_creation_function = False
        self.glade_file = glade_file
        self.data = {}
        self.data.update(config)
        self.input_dir, self.input_file = os.path.split(glade_file)
        base = os.path.splitext(self.input_file)[0]
        module = self.normalize_symbol(base)
        self.output_file = os.path.join(self.input_dir, module) + ".py"
        self.sax_parser = xml.sax.make_parser()
        self.sax_parser.setFeature(xml.sax.handler.feature_external_ges, False)
        self.sax_parser.setContentHandler(self)
        self.data["glade"] = self.input_file
        self.data["module"] = module
        self.data["date"] = time.asctime()

    def normalize_symbol (self, base):
        return "_".join( re.findall(tokenize.Name, base) )

    def capitalize_symbol (self, base):
        ClassName = "[a-zA-Z0-9]+"
        base = self.normalize_symbol(base)
        capitalize_map = lambda s : s[0].upper() + s[1:]
        return "".join( map(capitalize_map, re.findall(ClassName, base)) )

    def uncapitalize_symbol (self, base):
        InstanceName = "([a-z])([A-Z])"
        action = lambda m: "%s_%s" % ( m.groups()[0], m.groups()[1].lower() )
        base = self.normalize_symbol(base)
        base = base[0].lower() + base[1:]
        return re.sub(InstanceName, action, base)

    def startElement (self, name, attrs):
        if name == "widget":
            widget_id = attrs.get("id")
            widget_class = attrs.get("class")
            if not widget_id or not widget_class:
                raise NotGladeDocumentException(self)
            if not self.widgets_stack:
                self.creation_functions = []
                self.callbacks = []
                class_name = self.capitalize_symbol(widget_id)
                self.data["class"] = class_name
                self.data["root"] = widget_id
                self.roots_list.append(widget_id)
                self.code += class_format % self.data
            self.widgets_stack.append(widget_id)
        elif name == "signal":
            if not self.widgets_stack:
                raise NotGladeDocumentException(self)
            widget = self.widgets_stack[-1]
            signal_object = attrs.get("object")
            if signal_object:
                return
            handler = attrs.get("handler")
            if not handler:
                raise NotGladeDocumentException(self)
            if handler.startswith("gtk_"):
                return
            signal = attrs.get("name")
            if not signal:
                raise NotGladeDocumentException(self)
            self.data["widget"] = widget
            self.data["signal"] = signal
            self.data["handler"]= handler
            if handler not in self.callbacks:
                self.code += callback_format % self.data
                self.callbacks.append(handler)
        elif name == "property":
            if not self.widgets_stack:
                raise NotGladeDocumentException(self)
            widget = self.widgets_stack[-1]
            prop_name = attrs.get("name")
            if not prop_name:
                raise NotGladeDocumentException(self)
            if prop_name == "creation_function":
                self.parent_is_creation_function = True

    def characters (self, content):
        if self.parent_is_creation_function:
            if not self.widgets_stack:
                raise NotGladeDocumentException(self)
            handler = content.strip()
            if handler not in self.creation_functions:
                self.data["handler"] = handler
                self.code += creation_format % self.data
                self.creation_functions.append(handler)

    def endElement (self, name):
        if name == "property":
            self.parent_is_creation_function = False
        elif name == "widget":
            if not self.widgets_stack:
                raise NotGladeDocumentException(self)
            self.widgets_stack.pop()

    def write (self):
        self.data["t"] = self.indent
        self.code += header_format % self.data
        try:
            glade = open(self.glade_file, "r")
        except IOError, e:
            print >> sys.stderr, "Error opening glade file:", e
            return None
        try:
            try:
                self.sax_parser.parse(glade)
            finally:
                glade.close()
        except xml.sax._exceptions.SAXParseException, e:
            print >> sys.stderr, "Error parsing document:", e
            return None
        self.code += main_format % self.data

        for root in self.roots_list:
            self.data["class"] = self.capitalize_symbol(root)
            self.data["root"] = self.uncapitalize_symbol(root)
            self.code += instance_format % self.data

        self.data["root"] = self.uncapitalize_symbol(self.roots_list[0])
        self.code += run_format % self.data

        try:
            charset = config["charset"]
            fo = codecs.open(self.output_file, "w", charset)
            try:
                fo.write(self.code)
            finally:
                fo.close()
            print "Wrote", self.output_file
        except IOError, e:
            print >> sys.stderr, "Error writing output:", e
            return None
        return self.output_file

def usage (msg=None):
    program = sys.argv[0]
    if msg is not None:
        print "error:", msg
    print """\
Write a simple python file from a glade file.
Usage: %s [options] <file.glade>
Options:
  --charset=STRING
    Write files in given charset and add coding line.
  --copyright=STRING
    Write given copyright string after coding line.
  --license=FILENAME
    Add contents of given filename below copyright.
  --threads
    Call gtk.gdk.threads_init() before gtk.main().
""" % program

def which (program):
    if sys.platform.startswith("win"):
        exe_ext = ".exe"
    else:
        exe_ext = ""
    path_list =  os.environ["PATH"].split(os.pathsep)
    for path in path_list:
        program_path = os.path.join(path, program) + exe_ext
        if os.path.isfile(program_path):
            return program_path
    return None

def check_for_programs ():
    packages = {"diff" : "diffutils", "patch" : "patch"}
    for package in packages.keys():
        if not which(package):
            print >> sys.stderr, "Required program", package, "could not be found"
            print >> sys.stderr, "Is the package", packages[package], "installed?"
            if sys.platform.startswith("win"):
                print >> sys.stderr, "Download it from http://gnuwin32.sourceforge.net/packages.html"
            print >> sys.stderr, "Also, be sure it is in the PATH"
            return False
    return True

def is_older (filename):
    """
    Check if given filename is older that this program.
    """
    program = sys.argv[0]
    t0 = os.path.getmtime(program)
    t1 = os.path.getmtime(filename)
    return t0 > t1

def main (args):
    if not check_for_programs():
        return -1
    try:
        args = read_config(args)
    except getopt.GetoptError, msg:
        usage(msg)
        return -1
    if not args:
        usage()
        return -1
    code_writer = SimpleGladeCodeWriter(args[0])
    glade_file = code_writer.glade_file
    output_file = code_writer.output_file
    output_file_orig = output_file + ".orig"
    output_file_bak = output_file + ".bak"
    short_f = os.path.split(output_file)[1]
    short_f_orig = short_f + ".orig"
    short_f_bak = short_f + ".bak"
    helper_module = os.path.join(code_writer.input_dir,SimpleGladeApp_py)
    custom_diff = "custom.diff"

    exists_output_file = os.path.exists(output_file)
    exists_output_file_orig = os.path.exists(output_file_orig)
    if not exists_output_file_orig and exists_output_file:
        print >> sys.stderr, 'File %r exists' % short_f
        print >> sys.stderr, 'but %r does not.' % short_f_orig
        print >> sys.stderr, "That means your custom code would be overwritten."
        print >> sys.stderr, 'Please manually remove %r' % short_f
        print >> sys.stderr, "from this directory."
        print >> sys.stderr, "Anyway, I'll create a backup for you in %r." % short_f_bak
        shutil.copy(output_file, output_file_bak)
        return -1
    if exists_output_file_orig and exists_output_file:
        os.system("diff -U1 %s %s > %s" % \
                  (output_file_orig, output_file, custom_diff) )
        if not code_writer.write():
            os.remove(custom_diff)
            return -1
        shutil.copy(output_file, output_file_orig)
        if os.system("patch -fp0 < %s" % custom_diff):
            os.remove(custom_diff)
            return -1
        os.remove(custom_diff)
    else:
        if not code_writer.write():
            return -1
        shutil.copy(output_file, output_file_orig)
    os.chmod(output_file, 0755)
    if not os.path.isfile(helper_module) or is_older(helper_module):
        fo = codecs.open(helper_module, "w", "ascii")
        try:
            fo.write(SimpleGladeApp_content % config)
        finally:
            fo.close()
        print "Wrote", helper_module
    return 0


SimpleGladeApp_py = "SimpleGladeApp.py"

SimpleGladeApp_content = u"""\
# -*- coding: ascii -*-
# Copyright (C) 2004 Sandino Flores Moreno

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA
"Module that provides an object oriented abstraction to pygtk and libglade."

import os
import sys
import weakref
try:
    import gtk
    import gtk.glade
except ImportError:
    print >> sys.stderr, "Error importing pygtk2 and pygtk2-libglade"
    sys.exit(1)

class SimpleGladeApp (dict):

    def __init__ (self, glade_filename,
                  main_widget_name=None, domain=None, **kwargs):
        if os.path.isfile(glade_filename):
            self.glade_path = glade_filename
        else:
            glade_dir = os.path.split(sys.argv[0])[0]
            self.glade_path = os.path.join(glade_dir, glade_filename)
            for key, value in kwargs.items():
                try:
                    setattr(self, key, weakref.proxy(value))
                except TypeError:
                    setattr(self, key, value)
        self.glade = None
        gtk.glade.set_custom_handler(self.custom_handler)
        self.glade = gtk.glade.XML(self.glade_path, main_widget_name, domain)
        if main_widget_name:
            self.main_widget = self.glade.get_widget(main_widget_name)
        else:
            self.main_widget = None
        self.signal_autoconnect()
        self.new()

    def signal_autoconnect (self):
        signals = {}
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if callable(attr):
                signals[attr_name] = attr
        self.glade.signal_autoconnect(signals)

    def custom_handler (self,
            glade, function_name, widget_name,
            str1, str2, int1, int2):
        if hasattr(self, function_name):
            handler = getattr(self, function_name)
            return handler(str1, str2, int1, int2)

    def __getattr__ (self, data_name):
        if data_name in self:
            return self[data_name]
        else:
            widget = self.glade.get_widget(data_name)
            if widget is not None:
                self[data_name] = widget
                return widget
            else:
                raise AttributeError, data_name

    def __setattr__ (self, name, value):
        self[name] = value

    def new (self):
        pass

    def on_keyboard_interrupt (self):
        pass

    def gtk_widget_show (self, widget, *args):
        widget.show()

    def gtk_widget_hide (self, widget, *args):
        widget.hide()

    def gtk_widget_grab_focus (self, widget, *args):
        widget.grab_focus()

    def gtk_widget_destroy (self, widget, *args):
        widget.destroy()

    def gtk_window_activate_default (self, widget, *args):
        widget.activate_default()

    def gtk_true (self, *args):
        return gtk.TRUE

    def gtk_false (self, *args):
        return gtk.FALSE

    def gtk_main_quit (self, *args):
        gtk.main_quit()

    def main (self):
        %(threads)s
        gtk.main()

    def quit (self):
        gtk.main_quit()

    def run (self):
        try:
            self.main()
        except KeyboardInterrupt:
            self.on_keyboard_interrupt()
"""

if __name__ == "__main__":
    exit_code = main(sys.argv[1:])
    sys.exit(exit_code)

