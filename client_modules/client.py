import socket
import json
import time
import datetime
from base64 import b64encode, b64decode
import os
import select
import sys
from base64 import b64decode,b64encode

sys.path.insert(1, os.path.join(sys.path[0], '..'))
import security


BUFFER_SIZE = 32 * 1024

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

        self.priv_key =  security.RSA_generate_priv()
        self.pub_key = security.RSA_generate_pub( self.priv_key )
        self.sv_pub_key = None
        self.client_name = "nome blablabla"
        self.buffer = []

    def join_server( self, ip, port ):
        try:
            self.sock.connect( ( ip, port ) )
        except:
            print( "Connpriv_keyfailed")
            return

        key = self.wait_for_reply("pub_key")
        self.sv_pub_key = security.RSA_load_key( key )
        
        msg = {
            "intent": "register",
            "name": self.client_name,
            "pub_key":  security.RSA_key_bytes( self.pub_key )
        }
        msg = json.dumps(msg).encode()
        self.sock.send(msg)
    
    
    def get_tables( self ):
        request = {"intent" : "get_table_list"}
        request = json.dumps(request).encode()
        self.sock.send(request)
        reply = self.wait_for_reply()
        return reply.get("table_list")


    def join_table( self, table_id ):
        request = {
            "intent" : "join_table",
            "table_id" : table_id
        }
        request = json.dumps(request).encode()
        self.sock.send(request)
        return self.wait_for_reply( "table_info" )


    def create_table( self ):
        request = {"intent" : "create_table"}
        request = json.dumps( request ).encode()
        self.sock.send( request )
        return self.wait_for_reply( "table_info" )


    def relay_data( self, table_id, data, p ):
        msg = {
            "intent": "relay",
            "table_id": table_id,
            "relay_to": p.num,
            "data": data
        }
        msg = json.dumps(msg).encode()
        self.sock.send(msg)


    # Waits for a reply from server( blocking )
    def wait_for_reply( self, expected_reply=None, buffer=BUFFER_SIZE):
        if self.buffer:
            reply = self.buffer.pop(0)
            print("Processing: ", reply)
        else:
            received, addr = self.sock.recvfrom( buffer )
            if not received:
                print("Server side error!\nClosing client")
                exit()

            print( "\nReceived:", received)
            reply = received.decode().rstrip()
            reply = reply.split("---EOM---")
            
            if len(reply) > 1:
                self.buffer += reply[1:-1]
            reply = reply[0]
        
        reply = json.loads(reply)
        if "error" in reply.keys():
            print( "ERROR:", reply[ "error" ])
            return False

        if expected_reply:
            return reply.get( expected_reply )
        return reply


    # Waits for either a server reply or user input ( non blocking )
    def wait_for_reply_or_input( self, expected_reply=None, ok_cmds=[]):
        read_list = [self.sock, sys.stdin]
        while True:
            reply = None
            if self.buffer:
                reply = self.buffer.pop(0)
                print("Processing:\n\n", reply)
            else:
                readable, writable, errored = select.select( read_list, [], [])
                for s in readable:
                    if sys.stdin in readable:
                        cmd = sys.stdin.readline()
                        if cmd:
                            cmd = cmd.strip().lower()
                            if cmd in ok_cmds:
                                return None, cmd
                            else:
                                print( "Invalid command!")
                    else:
                        reply = s.recv( BUFFER_SIZE ).decode().rstrip()
                        print( "Received:", reply )
                        reply = reply.split("---EOM---")
                        if len(reply) > 1:
                            self.buffer += reply[1:-1]
                        reply = reply[0]
                        
            if reply:
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
