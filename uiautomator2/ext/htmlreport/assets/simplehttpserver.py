#!/usr/bin/env python
# coding: utf-8

import http.server as SimpleHTTPServer
import socket
import socketserver as SocketServer
import webbrowser
from contextlib import closing


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


def main():
    PORT = free_port()
    Handler = SimpleHTTPServer.SimpleHTTPRequestHandler
    httpd = SocketServer.TCPServer(("", PORT), Handler)

    # There is a bug that you have to refresh web page so you can see htmlreport
    # Even I tried to use threading to delay webbrowser open tab
    # but still need to refresh to let report show up.
    # I guess this is SimpleHTTPServer bug
    webbrowser.open('http://127.0.0.1:%d' % PORT, new=2)
    print("serving at port", PORT)
    httpd.serve_forever(0.1)


if __name__ == '__main__':
    main()