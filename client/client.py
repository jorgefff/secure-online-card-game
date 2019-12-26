import socket
import json
import time
import datetime
import os, sys, select
from base64 import b64encode, b64decode
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import security
from cc import CitizenCard

BUFFER_SIZE = 64 * 1024

EOM = '---EOM---'

class Client:
    def __init__( self, ip, port ):
        self.cc = CitizenCard()
        self.sock = socket.socket( 
            socket.AF_INET, 
            socket.SOCK_STREAM
        )
        self.sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR, 1
        )
        self.sock.bind((ip, port))
        self.priv_key =  security.RSA_generate_priv()
        self.pub_key = security.RSA_generate_pub( self.priv_key )
        self.sv_pub_key = None
        self.buffer = []

    def join_server( self, ip, port ):
        try:
            self.sock.connect( ( ip, port ) )
        except:
            print( "Connection failed" )
            return

        reply = self.wait_for_reply()
        key = reply['message']['pub_key']
        self.sv_pub_key = security.RSA_load_key( key )
        
        msg = {
            'intent': 'register',
            'name': self.cc.name,
            'pub_key':  security.RSA_sendable_key( self.pub_key ),
            'certificate': self.cc.sendable_cert,
            'chain': self.cc.sendable_chain
        }

        # Sign with citizen card
        signature = self.cc.sign(
            msg_fields=[
                msg['intent'],
                msg['name'],
                msg['pub_key'],
                msg['certificate'],
                str(msg['chain']),
            ]
        )

        # Send message
        msg = {
            'message' : msg,
            'signature' : b64encode(signature).decode('utf-8')
        }
        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())
    
    
    def get_tables( self ):
        request = {
            'message': {
                'intent' : 'get_table_list'
            }
        }
        request = json.dumps(request) + EOM
        self.sock.send(request.encode())
        reply = self.wait_for_reply()
        return reply['table_list']


    def join_table( self, table_id ):
        request = {
            'message': {
                'intent' : 'join_table',
                'table_id' : table_id
            }
        }
        request = json.dumps(request) + EOM
        self.sock.send(request.encode())
        reply = self.wait_for_reply()
        return reply['message']['table_info']


    def create_table( self ):
        request = {
            'message': {
                'intent': 'create_table'
            } 
        }
        request = json.dumps(request) + EOM
        self.sock.send(request.encode())
        reply = self.wait_for_reply()
        return reply['message']['table_info']


    def relay_data( self, table_id, data, p ):
        msg = {
            'message': {
                'intent': 'relay',
                'table_id': table_id,
                'relay_to': p.num,
                'message': data,
            }
        }
        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())


    # Waits for a reply from server( blocking )
    def wait_for_reply( self, expected_reply=None, bypass_buffer=False ):
        if not bypass_buffer and self.buffer:
            reply = self.buffer.pop(0)
            print("Processing: ", reply)
        else:
            received, addr = self.sock.recvfrom( BUFFER_SIZE )
            if not received:
                print("Server side error!\nClosing client")
                exit()

            print( "\nReceived:", received)
            reply = received.decode().rstrip()
            reply = reply.split(EOM)
            
            if len(reply) > 1:
                self.buffer += reply[1:-1]
            reply = reply[0]
        
        reply = json.loads(reply)
        if 'error' in reply['message'].keys():
            print( "ERROR:", reply['message']['error'])
            return False, False

        return reply


    # Waits for either a server reply or user input ( non blocking )
    def wait_for_reply_or_input( self, expected_reply=None, bypass_buffer=False, valid_cmds=[] ):
        read_list = [self.sock, sys.stdin]
        while True:
            reply = None
            if not bypass_buffer and self.buffer:
                reply = self.buffer.pop(0)
                print("Processing:\n\n", reply)
            else:
                readable, writable, errored = select.select( read_list, [], [])
                for s in readable:
                    if sys.stdin in readable:
                        cmd = sys.stdin.readline()
                        if cmd:
                            cmd = cmd.strip().lower()
                            if cmd in valid_cmds:
                                return None, cmd
                            else:
                                print( "Invalid command!")
                    else:
                        received = s.recv( BUFFER_SIZE ).decode().rstrip()
                        print( "Received:", received )
                        if not received:
                            print("Server disconnected")
                            exit()
                        reply = received.split(EOM)
                        if len(reply) > 1:
                            self.buffer += reply[1:-1]
                        reply = reply[0]
                        
            if reply:
                reply = json.loads(reply)
                if 'error' in reply['message'].keys():
                    print( "ERROR:", reply['message']['error'])
                    return False, False
                
                return reply, None

    def send(self, msg):
        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())
