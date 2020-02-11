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
    def __init__(self, ip, port):
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
        self.dh = security.Diffie_Hellman()
        self.dh.generate_keys()
        self.sv_dh = None
        self.buffer = []


    def join_server(self, ip, port):
        try:
            self.sock.connect((ip, port))
        except Exception as e:
            print("Connection failed")
            print(str(e))
            return False

        reply = self.wait_for_reply()
        self.sv_dh = security.DH_Params()
        self.sv_dh.load_key(reply['message']['pub_key'])
        self.sv_dh.load_iv(reply['message']['iv'])
        
        msg = {
            'intent': 'register',
            'name': self.cc.name,
            'pub_key': self.dh.share_key(),
            'iv': self.dh.share_iv(),
            'certificate': self.cc.sendable_cert,
            'chain': self.cc.sendable_chain
        }

        signature = self.cc.sign(json.dumps(msg))
        signature = b64encode(signature).decode('utf-8')

        # Send message
        msg = {
            'message' : msg,
            'signature' : signature
        }
        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())
        return True
    
    
    def get_tables(self):
        request = {
            'message': {
                'intent' : 'get_table_list'
            }
        }
        request = json.dumps(request) + EOM
        self.sock.send(request.encode())
        reply = self.wait_for_reply()
        return reply['message']['table_list']


    def join_table(self, table_id):
        msg = {
            'intent' : 'join_table',
            'table_id' : table_id
        }           
        signature = self.dh.sign(json.dumps(msg))
        signature = b64encode(signature).decode('utf-8')
        
        request = {
            'message': msg,
            'signature': signature,
        }
        
        request = json.dumps(request) + EOM
        self.sock.send(request.encode())
        reply = self.wait_for_reply()
        if not reply:
            return False


        return reply['message']['table_info']


    def create_table(self):
        msg = {'intent': 'create_table'}
        signature = self.dh.sign(json.dumps(msg))
        signature = b64encode(signature).decode('utf-8')
        request = {
            'message': msg,
            'signature': signature,
        }

        request = json.dumps(request) + EOM
        self.sock.send(request.encode())
        reply = self.wait_for_reply()
        if not reply:
            return False
        return reply['message']['table_info']


    def relay_data(self, table_id, data, dst, dh=None, cipher=False):
        if cipher:
            data = json.dumps(data)
            data = self.dh.encrypt(data, dh.public_key).decode('utf-8')
        
        msg = {
            'intent': 'relay',
            'table_id': table_id,
            'relay_to': dst,
            'relay': data,
        }
        signature = self.dh.sign(json.dumps(msg))
        signature = b64encode(signature).decode('utf-8')
        
        msg = {
            'message': msg,
            'signature': signature,
        }

        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())


    def load_relayed_data(self, ciph_data, dh):    
        data = self.dh.decrypt(ciph_data, dh.public_key, dh.iv)
        data = json.loads(data)
        # print("Relayed to me:", data)
        return data


    def validate_pre_game(self, table_id, data):
        msg = {
            'intent': 'validate_pre_game',
            'table_id': table_id,
            'data': data,
        }

        signature = self.dh.sign(json.dumps(msg))
        signature = b64encode(signature).decode('utf-8')
        
        msg = {
            'message': msg,
            'signature': signature,
        }

        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())


    def make_play(self, table_id, card):
        play = {
            'intent': 'play',
            'table_id': table_id,
            'card': card,
        }

        signature = self.dh.sign(json.dumps(play))
        signature = b64encode(signature).decode('utf-8')

        msg = {
            'message': play,
            'signature': signature,
        }

        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())


    # Waits for a reply from server (blocking)
    def wait_for_reply(self, bypass_buffer=False):
        if not bypass_buffer and self.buffer:
            reply = self.buffer.pop(0)
            #print("Processing: ", reply)
        else:
            received, addr = self.sock.recvfrom(BUFFER_SIZE)
            if not received:
                print("Server side error!\nClosing client")
                exit()

            #print("\nReceived:", received)
            reply = received.decode().rstrip()
            reply = reply.split(EOM)
            
            if len(reply) > 1:
                self.buffer += reply[1:-1]
            reply = reply[0]
        
        reply = json.loads(reply)
        
        if 'signature' not in reply.keys():
            print("Unsigned message")
            return False

        if self.sv_dh is not None:
            signature = b64decode(reply['signature'])
            if not self.sv_dh.valid_signature(
                    json.dumps(reply['message']), 
                    signature):
                print("Invalid signature!")
                return False

        if 'error' in reply['message'].keys():
            print("ERROR:", reply['message']['error'])
            return False
        
        return reply


    # Waits for either a server reply or user input (non blocking)
    def wait_for_reply_or_input(self, bypass_buffer=False, valid_cmds=[]):
        read_list = [self.sock, sys.stdin]
        while True:
            reply = None
            if not bypass_buffer and self.buffer:
                reply = self.buffer.pop(0)
                #print("Processing:\n\n", reply)
            else:
                readable, writable, errored = select.select(read_list, [], [])
                for s in readable:
                    if sys.stdin in readable:
                        cmd = sys.stdin.readline()
                        if cmd:
                            cmd = cmd.strip().lower()
                            if cmd in valid_cmds:
                                return None, cmd
                            else:
                                print("Invalid command!")
                    else:
                        received = s.recv(BUFFER_SIZE).decode().rstrip()
                        print("Received:", received)
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
                    print("ERROR:", reply['message']['error'])
                    return False, False
                
                if 'signature' not in reply.keys():
                    print("Unsigned message")
                    return False, False

                signature = b64decode(reply['signature'])

                if not self.sv_dh.valid_signature(
                        json.dumps(reply['message']), 
                        signature):
                    #print("Invalid signature!")
                    return False, False

                return reply, None

    def send(self, msg):
        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())
