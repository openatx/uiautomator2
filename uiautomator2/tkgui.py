#!/usr/bin/env python
# coding: utf-8
#
# > How to get tkinter canvas to dynamically resize to window width?
# http://stackoverflow.com/questions/22835289/how-to-get-tkinter-canvas-to-dynamically-resize-to-window-width
#
# > Canvas tutoril
# http://www.tkdocs.com/tutorial/canvas.html
#
# > Canvas API reference
# http://effbot.org/tkinterbook/canvas.htm
#
# > Tutorial canvas tk
# http://www.tutorialspoint.com/python/tk_canvas.htm

import os
import time
import threading
import logging
import six

import uiautomator2
from PIL import Image, ImageTk

if six.PY3:
    from queue import Queue
    import tkinter as tk
    from tkinter import simpledialog as tkSimpleDialog
    from tkinter import filedialog as tkFileDialog
else:
    from Queue import Queue
    import Tkinter as tk
    import tkSimpleDialog
    import tkFileDialog



log = logging.getLogger('') #logutils.getLogger('tkgui')
log.setLevel(logging.DEBUG)


def insert_code(filename, code, save=True, marker='# ATX CODE END'):
    """ Auto append code """
    content = ''
    found = False
    for line in open(filename, 'rb'):
        if not found and line.strip() == marker:
            found = True
            cnt = line.find(marker)
            content += line[:cnt] + code
        content += line
    if not found:
        if not content.endswith('\n'):
            content += '\n'
        content += code + marker + '\n'
    if save:
        with open(filename, 'wb') as f:
            f.write(content)
    return content

class CropIDE(object):
    def __init__(self, title='AirtestX Basic GUI', ratio=0.5, device=None):
        self._device = device
        self._root = tk.Tk()
        self._root.title(title)
        self._queue = Queue()

        self._refresh_text = tk.StringVar()
        self._refresh_text.set("Refresh")
        self._gencode_text = tk.StringVar()
        self._genfile_name = tk.StringVar()
        self._fileext_text = tk.StringVar()
        self._auto_refresh_var = tk.BooleanVar()
        self._attachfile_text = tk.StringVar()
        self._running = False # if background is running

        self._init_items()
        self._init_thread()
        self._init_refresh()

        self._lastx = 0
        self._lasty = 0
        self._bounds = None # crop area
        self._center = (0, 0) # center point
        self._offset = (0, 0) # offset to image center
        self._poffset = (0, 0)
        self._size = (90, 90)
        self._moved = False # click or click and move
        self._color = 'red' # draw color
        self._tkimage = None # keep reference
        self._image = None
        self._ratio = ratio
        self._selected_node = None
        self._hovered_node = None
        self._save_parent_dir = None

        self._init_vars()

    def _init_items(self):
        """
        .---------------.
        | Ctrl | Screen |
        |------|        |
        | Code |        |
        |      |        |
        """
        root = self._root
        root.resizable(0, 0)

        frm_control = tk.Frame(root, bg='#bbb')
        frm_control.grid(column=0, row=0, padx=5, sticky=tk.NW)
        frm_screen = tk.Frame(root, bg='#aaa')
        frm_screen.grid(column=1, row=0)

        frm_screenshot = tk.Frame(frm_control)
        frm_screenshot.grid(column=0, row=0, sticky=tk.W)
        tk.Label(frm_control, text='-'*30).grid(column=0, row=1, sticky=tk.EW)
        frm_code = tk.Frame(frm_control)
        frm_code.grid(column=0, row=2, sticky=tk.EW)

        self._btn_refresh = tk.Button(frm_screenshot, textvariable=self._refresh_text, command=self._refresh_screen)
        self._btn_refresh.grid(column=0, row=0, sticky=tk.W)
        # tk.Button(frm_screenshot, text="Wakeup", command=self._device.wakeup).grid(column=0, row=1, sticky=tk.W)
        tk.Button(frm_screenshot, text=u"保存选中区域", command=self._save_crop).grid(column=0, row=1, sticky=tk.W)
        
        # tk.Button(frm_screenshot, text="保存截屏", command=self._save_screenshot).grid(column=0, row=2, sticky=tk.W)
        frm_checkbtns = tk.Frame(frm_screenshot)
        frm_checkbtns.grid(column=0, row=3, sticky=(tk.W, tk.E))
        tk.Checkbutton(frm_checkbtns, text="Auto refresh", variable=self._auto_refresh_var, command=self._run_check_refresh).grid(column=0, row=0, sticky=tk.W)

        frm_code_editor = tk.Frame(frm_code)
        frm_code_editor.grid(column=0, row=0, sticky=(tk.W, tk.E))
        tk.Label(frm_code_editor, text='Generated code').grid(column=0, row=0, sticky=tk.W)
        tk.Entry(frm_code_editor, textvariable=self._gencode_text, width=30).grid(column=0, row=1, sticky=tk.W)
        tk.Label(frm_code_editor, text='Save file name').grid(column=0, row=2, sticky=tk.W)
        tk.Entry(frm_code_editor, textvariable=self._genfile_name, width=30).grid(column=0, row=3, sticky=tk.W)
        tk.Label(frm_code_editor, text='Extention name').grid(column=0, row=4, sticky=tk.W)
        tk.Entry(frm_code_editor, textvariable=self._fileext_text, width=30).grid(column=0, row=5, sticky=tk.W)
        
        frm_code_btns = tk.Frame(frm_code)
        frm_code_btns.grid(column=0, row=2, sticky=(tk.W, tk.E))
        tk.Button(frm_code_btns, text='Run', command=self._run_code).grid(column=0, row=0, sticky=tk.W)
        self._btn_runedit = tk.Button(frm_code_btns, state=tk.DISABLED, text='Insert and Run', command=self._run_and_insert)
        self._btn_runedit.grid(column=1, row=0, sticky=tk.W)
        tk.Button(frm_code, text='Select File', command=self._run_selectfile).grid(column=0, row=4, sticky=tk.W)
        tk.Label(frm_code, textvariable=self._attachfile_text).grid(column=0, row=5, sticky=tk.W)
        tk.Button(frm_code, text='Reset', command=self._reset).grid(column=0, row=6, sticky=tk.W)

        self.canvas = tk.Canvas(frm_screen, bg="blue", bd=0, highlightthickness=0, relief='ridge')
        self.canvas.grid(column=0, row=0, padx=10, pady=10)
        self.canvas.bind("<Button-1>", self._stroke_start)
        self.canvas.bind("<B1-Motion>", self._stroke_move)
        self.canvas.bind("<B1-ButtonRelease>", self._stroke_done)
        self.canvas.bind("<Motion>", self._mouse_move)

    def _init_vars(self):
        self.draw_image(self._device.screenshot())

    def _worker(self):
        que = self._queue
        while True:
            (func, args, kwargs) = que.get()
            try:
                func(*args, **kwargs)
            except Exception as e:
                print(e)
            finally:
                que.task_done()
    
    def _run_check_refresh(self):
        auto = self._auto_refresh_var.get()
        state = tk.DISABLED if auto else tk.NORMAL
        self._btn_refresh.config(state=state)

    def _run_async(self, func, args=(), kwargs={}):
        self._queue.put((func, args, kwargs))

    def _init_thread(self):
        th = threading.Thread(name='thread', target=self._worker)
        th.daemon = True
        th.start()

    def _init_refresh(self):
        if not self._running and self._auto_refresh_var.get():
            self._refresh_screen()
        self._root.after(200, self._init_refresh)

    def _fix_bounds(self, bounds):
        bounds = [x/self._ratio for x in bounds]
        (x0, y0, x1, y1) = bounds
        if x0 > x1:
            x0, y0, x1, y1 = x1, y1, x0, y0
        # in case of out of bounds
        w, h = self._size
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(w, x1)
        y1 = min(h, y1)
        return map(int, [x0, y0, x1, y1])

    @property
    def select_bounds(self):
        if self._bounds is None:
            return None
        return self._fix_bounds(self._bounds)

    def _fix_path(self, path):
        try:
            return os.path.relpath(path, os.getcwd())
        except:
            return path

    def _save_screenshot(self):
        save_to = tkFileDialog.asksaveasfilename(**dict(
            defaultextension=".png",
            filetypes=[('PNG', '.png')],
            title='Select file'))
        if not save_to:
            return
        log.info('Save to: %s', save_to)
        self._image.save(save_to)    

    def _save_crop(self):
        log.debug('crop bounds: %s', self._bounds)
        if self._bounds is None:
            return
        bounds = self.select_bounds
        # ext = '.%dx%d.png' % tuple(self._size)
        # tkFileDialog doc: http://tkinter.unpythonic.net/wiki/tkFileDialog
        save_to = tkFileDialog.asksaveasfilename(**dict(
            initialdir=self._save_parent_dir,
            defaultextension=".png",
            filetypes=[('PNG', ".png")],
            title='Select file'))
        if not save_to:
            return
        save_to = self._fix_path(save_to)
        # force change extention with info (resolution and offset)
        save_to = os.path.splitext(save_to)[0] + self._fileext_text.get()

        self._save_parent_dir = os.path.dirname(save_to)

        log.info('Crop save to: %s', save_to)
        self._image.crop(bounds).save(save_to)
        self._genfile_name.set(os.path.basename(save_to))
        self._gencode_text.set('d.click_image(r"%s")' % save_to)

    def _run_code(self):
        d = self._device
        logging.debug("run code: %s", d)
        code = self._gencode_text.get()
        exec(code)

    def _run_and_insert(self):
        self._run_code()
        filename = self._attachfile_text.get().strip()
        code_snippet = self._gencode_text.get().strip()
        if filename and code_snippet:
            insert_code(filename, code_snippet+'\n')

    def _run_selectfile(self):
        filename = tkFileDialog.askopenfilename(**dict(
            filetypes=[('All files', '.*'), ('Python', '.py')],
            title='Select file'))
        self._attachfile_text.set(filename)
        if filename:
            self._btn_runedit.config(state=tk.NORMAL)
        print(filename)

    def _refresh_screen(self):
        def foo():
            self._running = True
            image = self._device.screenshot()
            self.draw_image(image)
            self._refresh_text.set("Refresh")

            self._draw_lines()
            self._running = False

        self._run_async(foo)
        self._refresh_text.set("Refreshing ...")

    def _stroke_start(self, event):
        self._moved = False
        c = self.canvas
        self._lastx, self._lasty = c.canvasx(event.x), c.canvasy(event.y)
        log.debug('mouse position: %s', (self._lastx, self._lasty))

    def _stroke_move(self, event):
        self._moved = True
        self._reset()
        c = self.canvas
        x, y = c.canvasx(event.x), c.canvasy(event.y)
        self._bounds = (self._lastx, self._lasty, x, y)
        self._center = (self._lastx+x)/2, (self._lasty+y)/2
        self._draw_lines()

    def _stroke_done(self, event):
        c = self.canvas
        x, y = c.canvasx(event.x), c.canvasy(event.y)
        if self._moved: # drag action
            x, y = (self._lastx+x)/2, (self._lasty+y)/2
            self._offset = (0, 0)
        else:
            # click action
            if self._bounds is None:
                cx, cy = (x/self._ratio, y/self._ratio)
                self._gencode_text.set('d.click(%d, %d)' % (cx, cy))
            else:
                (x0, y0, x1, y1) = self.select_bounds
                ww, hh = x1-x0, y1-y0
                cx, cy = (x/self._ratio, y/self._ratio)
                mx, my = (x0+x1)/2, (y0+y1)/2 # middle
                self._offset = (offx, offy) = map(int, (cx-mx, cy-my))
                poffx = ww and round(offx*100.0/ww) # in case of ww == 0
                poffy = hh and round(offy*100.0/hh)
                self._poffset = (poffx, poffy)
                self._gencode_text.set('(%d, %d)' % (cx, cy)) #offset=(%.2f, %.2f)' % (poffx/100, poffy/100))
                # self._gencode_text.set('offset=(%.2f, %.2f)' % (poffx/100, poffy/100))

        ext = ".%dx%d" % tuple(self._size)
        if self._poffset != (0, 0):
            px, py = self._poffset
            ext += '.%s%d%s%d' % (
                'R' if px > 0 else 'L', abs(px), 'B' if py > 0 else 'T', abs(py))
        ext += '.png'
        self._fileext_text.set(ext)
        self._center = (x, y) # rember position
        self._draw_lines()
        self.canvas.itemconfigure('select-bounds', width=2)

    def draw_image(self, image):
        self._image = image
        self._size = (width, height) = image.size
        w, h = int(width*self._ratio), int(height*self._ratio)
        image = image.copy()
        image.thumbnail((w, h), Image.ANTIALIAS)
        tkimage = ImageTk.PhotoImage(image)
        self._tkimage = tkimage # keep a reference
        self.canvas.config(width=w, height=h)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=tkimage)

    def _draw_bounds(self, bounds, color=None, tags='select-bounds'):
        if not color:
            color=self._color
        c = self.canvas
        (x0, y0, x1, y1) = bounds
        c.create_rectangle(x0, y0, x1, y1, outline=color, tags='select-bounds', width=2)

    def _draw_lines(self):
        if self._center and self._center != (0, 0):
            x, y = self._center
            self.draw_point(x, y)
        if self._bounds:
            self._draw_bounds(self._bounds)
        if self._hovered_node:
            # print self._hovered_node.bounds
            bounds = [v*self._ratio for v in self._hovered_node.bounds]
            self._draw_bounds(bounds, color='blue', tags='ui-bounds')

    def _reset(self):
        self._bounds = None
        self._offset = (0, 0)
        self._poffset = (0, 0)
        self._center = (0, 0)
        self.canvas.delete('select-bounds')
        self.canvas.delete('select-point')

    def _mouse_move(self, event):
        pass

    def draw_point(self, x, y):
        self.canvas.delete('select-point')
        r = max(min(self._size)/30*self._ratio, 5)
        self.canvas.create_line(x-r, y, x+r, y, width=2, fill=self._color, tags='select-point')
        self.canvas.create_line(x, y-r, x, y+r, width=2, fill=self._color, tags='select-point')

    def mainloop(self):
        self._root.mainloop()
        

def main(address, scale=0.3):
    log.debug("gui starting(scale: {}) ...".format(scale))
    d = uiautomator2.connect(address)
    title = 'GUI ' + d.serial
    gui = CropIDE(title, ratio=scale, device=d)
    gui.mainloop()

def test():
    # image = Image.open('jurassic_park_kitchen.jpg')
    gui = CropIDE('AirtestX IDE')
    image = Image.open('screen.png')
    gui.draw_image(image)
    gui.draw_point(100, 100)
    gui.mainloop()


if __name__ == '__main__':
    main(None)