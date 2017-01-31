#!/usr/bin/env python
#
#   Copyright (C) 2016 Sean D'Epagnier
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.  

from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, Namespace, emit, join_room, leave_room, \
    close_room, rooms, disconnect

pypilot_webapp_port=80

# Set this variable to "threading", "eventlet" or "gevent" to test the
# different async modes, or leave it set to None for the application to choose
# the best option based on installed packages.
async_mode = None

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode)

import select, socket, json
DEFAULT_PORT = 21311

class LineBufferedNonBlockingSocket():
    def __init__(self, connection):
        connection.setblocking(0)

        self.socket = connection
        self.in_buffer = ''
        self.out_buffer = ''
        self.no_newline = True

    def send(self, data):
        self.out_buffer += data

    def flush(self):
        if not len(self.out_buffer):
            return

        try:
            count = self.socket.send(self.out_buffer)
            self.out_buffer = self.out_buffer[count:]
        except:
            self.socket.close()

    def recv(self):
        size = 4096
        try:
            data = self.socket.recv(size)
        except:
            return

        self.no_newline = False
        self.in_buffer += data
        l = len(data)
        if l == 0:
            return False
        if l == size:
            return l+self.recv()
        return l

    def readline(self):
        if self.no_newline:
            return False
        pos = 0
        for c in self.in_buffer:
            if c=='\n':
                ret = self.in_buffer[:pos]
                self.in_buffer = self.in_buffer[pos+1:]
                return ret
            pos += 1
        self.no_newline = True
        return False

class Connection():
    def __init__(self):
        socketio.start_background_task(target=self.background_thread)
        self.client = False

    def background_thread(self):
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        while True:
            socketio.emit('flush') # unfortunately needed to awaken socket for client messages
            try:
                connection.connect(('localhost', DEFAULT_PORT))
                break
            except:
                socketio.sleep(2)

        socketio.emit('signalk_connect')

        self.client = LineBufferedNonBlockingSocket(connection)
#        self.client.send(json.dumps({'method': 'list'}) + '\n')
        
        while True:
            line = self.client.readline()
            if line:
                try:
                    socketio.emit('signalk', {'data': json.loads(line.rstrip())})
                except:
                    socketio.emit('log', line)
                    print 'error: ', line.rstrip()

            else:
                self.client.flush()
                self.client.recv()
                socketio.sleep(.1)

@app.route('/')
def index():
    return render_template('index.html', async_mode=socketio.async_mode, pypilot_webapp_port=pypilot_webapp_port)

class MyNamespace(Namespace):
    def __init__(self, name):
        super(Namespace, self).__init__(name)
        self.clients = {}

    def on_signalk(self, message):
        #print message
        self.clients[request.sid].client.send(json.dumps(message) + '\n')

    def on_disconnect_request(self):
        print 'disconnect'
        disconnect()

    def on_ping(self):
        emit('pong')

    def on_connect(self):
        self.clients[request.sid] = Connection()
        print('Client connected', request.sid, len(self.clients))

    def on_disconnect(self):
        client = self.clients[request.sid].client
        if client:
            client.socket.close()
        del self.clients[request.sid]
        print('Client disconnected', request.sid, len(self.clients))

socketio.on_namespace(MyNamespace(''))

def main():
    import os
    os.chdir(os.path.abspath(os.path.dirname(__file__)))
    socketio.run(app, debug=False, host='0.0.0.0', port=pypilot_webapp_port)

if __name__ == '__main__':
    main()