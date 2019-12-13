import socket
import json
import time
import datetime
from base64 import b64encode, b64decode
import os
import select
import sys

sys.path.insert(1, os.path.join(sys.path[0], '..'))
import security


BUFFER_SIZE = 1024

class Client:
    def __init__( self, ip, port ):
        self.sock = socket.socket( 
            socket.AF_INET, 
            socket.SOCK_STREAM
        )
        self.sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR, 1
        )
        self.sock.bind((ip, port))

        self.priv_key =  security.generate_priv_key()
        self.pub_key = security.generate_pub_key( self.priv_key )
        self.sv_pub_key = None
        self.client_name = "nome blablabla"


    def join_server( self, ip, port ):
        try:
            self.sock.connect( ( ip, port ) )
        except:
            print( "Connection failed")
            return

        reply = self.wait_for_reply()
        self.sv_pub_key = security.load_key_from_bytes( reply.get("pub_key") )
        
        msg = {
            "intent": "register",
            "name": self.client_name,
            "pub_key":  security.get_key_bytes( self.pub_key )
        }
        msg = json.dumps(msg).encode()
        self.sock.send(msg)
    
    
    def get_tables( self ):
        request = {"intent" : "get_table_list"}
        request = json.dumps(request).encode()
        self.sock.send(request)
        reply = self.wait_for_reply()
        return reply.get("table_list")


    def join_table( self,table_id):
        request = {
            "intent" : "join_table",
            "table_id" : id
        }
        request = json.dumps(request).encode()
        self.sock.send(request)
        return self.wait_for_reply( "table_info" )


    def create_table( self ):
        request = {"intent" : "create_table"}
        request = json.dumps(request).encode()
        self.sock.send(request)
        return self.wait_for_reply( "table_info" )


    def relay_data( self, table_id, data, player_num, player_key):
        msg = {
            "intent": "relay",
            "table_id": table_id,
            "relay_to": player_num,
            "data": data
        }
        msg = json.dumps(msg).encode()
        self.sock.send(msg)


    # Waits for a reply from server( blocking)
    def wait_for_reply( self, expected_reply=None):
        received, addr = self.sock.recvfrom( BUFFER_SIZE)
        
        if not received:
            print("Server side error!\nClosing client")
            exit()
            
        reply = received.decode().rstrip()
        print( "\nReceived:", received)
        reply = json.loads(reply)
        
        if "error" in reply.keys():
            print( "ERROR:", reply[ "error" ])
            return False

        if expected_reply:
            return reply.get(expected_reply)
        return reply


    # Waits for either a server reply or user input( non blocking)
    def wait_for_reply_or_input( self, expected_reply=None, table_cmds=[]):
        read_list = [self.sock, sys.stdin]
        while True:
            readable, writable, errored = select.select( read_list, [], [])
            for s in readable:
                if sys.stdin in readable:
                    cmd = sys.stdin.readline()
                    if cmd:
                        cmd = cmd.strip().lower()
                        if cmd in table_cmds:
                            return None, cmd
                        else:
                            print( "Invalid command!")
                else:
                    reply = s.recv( BUFFER_SIZE).decode().rstrip()
                    print( "Received:", reply )
                    reply = json.loads(reply)
                    if "error" in reply.keys():
                        print( "ERROR:", reply.get("error"))
                        return False, False

                    if expected_reply:
                        return reply.get(expected_reply), None
                    return reply, None


    # Confirm you want to play with these players
    def send_pl_confirmation( self, table_id):
        #TODO: falta a identidade dos oponentes
        # "The croupier will only start the table after getting a signed statement
        # from all players including the identity of the opponents"
        msg = {
            "intent": "confirm_players",
            "table_id": table_id}
        msg = json.dumps(msg).encode()
        self.sock.send(msg)
