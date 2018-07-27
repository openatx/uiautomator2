#!/usr/bin/env python
# coding: utf-8

import six
import socket
from contextlib import closing
import webbrowser
import imageio, os

if six.PY2:
    import SimpleHTTPServer
    import SocketServer
else:
    import http.server as SimpleHTTPServer
    import socketserver as SocketServer
    

def is_port_avaiable(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    return result != 0


def free_port():
    if is_port_avaiable(11000):
        return 11000
    
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def img2video():
    images = []
    pwd = os.path.dirname(os.path.abspath(__file__))
    files = sorted(( pwd + '\\imgs\\' + pic for pic in os.listdir('.\\imgs') if pic.endswith('.jpg')))
    for filename in files:
        images.append(imageio.imread(filename))
    imageio.mimsave('.\\imgs\\video.mp4', images, fps=1)


def main():
    img2video()
    PORT = free_port()
    Handler = SimpleHTTPServer.SimpleHTTPRequestHandler
    httpd = SocketServer.TCPServer(("", PORT), Handler)

    webbrowser.open('http://127.0.0.1:%d' % PORT, new=2)
    print("serving at port", PORT)
    httpd.serve_forever(0.1)


if __name__ == '__main__':
    main()
