# Start a multithreaded WSGI Server for reprojecting map tiles for Google Earth

###############################################################################
# Copyright (c) 2018, Patrick Broxton
# 
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
# 
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
# 
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
###############################################################################

import sys,os
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
import multiprocessing.pool
prefix = os.path.dirname(os.path.realpath(__file__)) + os.path.sep
sys.path.insert(0, prefix)
from generate_tiles import generate_tiles
    
class ThreadPoolWSGIServer(WSGIServer):
    '''WSGI-compliant HTTP server.  Dispatches requests to a pool of threads.'''

    def __init__(self, thread_count=None, *args, **kwargs):
        '''If 'thread_count' == None, we'll use multiprocessing.cpu_count() threads.'''
        WSGIServer.__init__(self, *args, **kwargs)
        self.thread_count = thread_count
        self.pool = multiprocessing.pool.ThreadPool(self.thread_count)

    # Inspired by SocketServer.ThreadingMixIn.
    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except:
            self.handle_error(request, client_address)

    def process_request(self, request, client_address):
        self.pool.apply_async(self.process_request_thread, args=(request, client_address))


def make_server(host, port, app, thread_count=None, handler_class=WSGIRequestHandler):
    '''Create a new WSGI server listening on `host` and `port` for `app`'''
    httpd = ThreadPoolWSGIServer(thread_count, (host, port), handler_class)
    httpd.set_app(app)
    return httpd

    
if __name__ == '__main__':
    addr_file = os.path.abspath(__file__).replace(os.path.basename(__file__),'') + '/addr.txt'
    with open(addr_file) as f:
        for line in f:
            vals = line.split(' ')
            port = vals[2].strip()
                
    print('Tile reprojection server running on port ' + port)
    httpd = make_server('', int(port), generate_tiles)
    environ = dict(os.environ.items())
    environ['wsgi.errors']       = sys.stderr
    httpd.serve_forever()
