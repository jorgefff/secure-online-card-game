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
        self.sv_dh = security.DH_Params()
        # self.priv_key =  security.RSA_generate_priv()
        # self.pub_key = security.RSA_generate_pub(self.priv_key)
        # self.sv_pub_key = None
        self.buffer = []


    def join_server(self, ip, port):
        try:
            self.sock.connect((ip, port))
        except:
            print("Connection failed")
            return

        reply = self.wait_for_reply()
        self.sv_dh.load_key(reply['message']['pub_key'])
        self.sv_dh.load_iv(reply['message']['iv'])
        # self.sv_pub_key = security.RSA_load_key(key)
        
        msg = {
            'intent': 'register',
            'name': self.cc.name,
            # 'pub_key':  security.RSA_sendable_key(self.pub_key),
            'pub_key': self.dh.share_key(),
            'iv': self.dh.share_iv(),
            'certificate': self.cc.sendable_cert,
            'chain': self.cc.sendable_chain
        }

        # Sign with citizen card
       #  signature = self.cc.sign(
       #      msg_fields=[
       #          msg['intent'],
       #          msg['name'],
       #          msg['pub_key'],
       #          msg['iv'],
       #          msg['certificate'],
       #          str(msg['chain']),
       #      ]
       # )

        signature = self.cc.sign(json.dumps(msg))
        signature = b64encode(signature).decode('utf-8')

        # Send message
        msg = {
            'message' : msg,
            'signature' : signature
        }
        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())
    
    
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


    def create_table(self):
        request = {
            'message': {
                'intent': 'create_table'
            } 
        }
        request = json.dumps(request) + EOM
        self.sock.send(request.encode())
        reply = self.wait_for_reply()
        return reply['message']['table_info']


    def relay_data(self, table_id, data, dst, dh=None, cipher=False):
        if cipher:
            data = json.dumps(data)
            data = self.dh.encrypt(data, dh.public_key) #security.RSA_encrypt(p.pub_key, text_data).decode('utf-8')
            
        msg = {
            'message': {
                'intent': 'relay',
                'table_id': table_id,
                'relay_to': dst,
                'relay': data,
            }
        }
        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())

    def load_relayed_data(self, ciph_data, dh):    
        data = self.dh.decrypt(ciph_data, dh.public_key, dh.iv) #security.RSA_decrypt(self.priv_key, ciph_data)
        data = json.loads(data)
        print("Relayed to me:", data)
        return data

    # Waits for a reply from server (blocking)
    def wait_for_reply(self, bypass_buffer=False):
        if not bypass_buffer and self.buffer:
            reply = self.buffer.pop(0)
            print("Processing: ", reply)
        else:
            received, addr = self.sock.recvfrom(BUFFER_SIZE)
            if not received:
                print("Server side error!\nClosing client")
                exit()

            print("\nReceived:", received)
            reply = received.decode().rstrip()
            reply = reply.split(EOM)
            
            if len(reply) > 1:
                self.buffer += reply[1:-1]
            reply = reply[0]
        
        reply = json.loads(reply)
        if 'error' in reply['message'].keys():
            print("ERROR:", reply['message']['error'])
            return False, False

        return reply


    # Waits for either a server reply or user input (non blocking)
    def wait_for_reply_or_input(self, bypass_buffer=False, valid_cmds=[]):
        read_list = [self.sock, sys.stdin]
        while True:
            reply = None
            if not bypass_buffer and self.buffer:
                reply = self.buffer.pop(0)
                print("Processing:\n\n", reply)
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
                
                return reply, None

    def send(self, msg):
        msg = json.dumps(msg) + EOM
        self.sock.send(msg.encode())
