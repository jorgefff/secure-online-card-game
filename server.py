import socket 
import json
import select
import time
import datetime
import base64
import os
from sys import argv
import sys
import security

# Global vars
table_id_counter = 0
tables = {}
pre_registers = {}
clients = {}

# Address
IP = "localhost"
SERVER_PORT = 50000
SV_ADDR = (IP, SERVER_PORT)

# Socket configs
BUFFER_SIZE = 8 * 1024

# TCP Socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(SV_ADDR)


def pre_register_client( client_socket):
    priv_key = security.generate_priv_key()
    pub_key = security.generate_pub_key( priv_key )
    new_client = Client(
        socket=client_socket,
        name=None,
        sv_priv_key=priv_key,
        sv_pub_key=pub_key
    )
    pre_registers[client_socket] = new_client


def send_pub_key( client_socket ):
    c = pre_registers[ client_socket ]
    key = security.get_key_bytes( c.sv_pub_key )
    msg = {"pub_key" : key }
    msg = json.dumps(msg).encode().ljust(BUFFER_SIZE, b' ')
    client_socket.send( msg )


def register_client( msg, client_socket ):
    c = pre_registers.get( client_socket )
    
    key = msg.get("pub_key")

    c.name = msg.get("name")
    c.pub_key = security.load_key( key )
    
    clients[client_socket] = c
    del pre_registers[client_socket]


def send_table_list( client_socket ):
    table_list = []
    for table in tables.values():
        if table.state == "OPEN":
            table_list.append({
                "id": table.table_id,
                "title": table.title,
                "player_count": table.player_count,
                "max_players": table.max_player_count})

    msg = {"table_list": table_list}
    client_socket.send(msg)


def get_new_table_id():
    global table_id_counter
    new_id = table_id_counter
    table_id_counter += 1
    return new_id

    
def broadcast_new_player( players ):
    player = players[-1]
    new_player = {
        "name": player.client.name,
        "pub_key": security.get_key_bytes( player.client.pub_key ),
        "num": player.num 
    }

    for p in players[:-1]:
        msg = {
            "table_update": {
                "update": "new_player", 
                "new_player": new_player}}
        p.client.send(msg)


def broadcast_player_confirmation( players, pl_num ):
    for p in players:
        msg = {
            "table_update": {
                "update": "player_confirmation", 
                "player_num": pl_num}}
        p.client.send(msg)


def broadcast_state_change( players, new_state ):
    for p in players:
        msg = {
            "table_update": {
                "update": "table_state", 
                "table_state": new_state}}
        p.client.send(msg)


def broadcast_deck_keys( players):
    keys = {}
    for i in range(0, len(players)):
        keys[i] = players[i].deck_key
    
    keys = {"keys": keys}

    for p in players:
        p.send( keys )


def generate_deck():
    deck = []
    suits = ["Sp", "Cl", "He", "Di"] # Spades Clubs Hearts Diamonds
    specials = ["A", "K", "Q", "J"]  # Ace King Queen Jack
    for suit in suits:
        for sp in specials:
            deck.append( suit + "-" + sp )
        for n in range( 2,11 ):
            deck.append( suit + "-" + str( n ))
    return deck



def join_table_handler (msg, client):
    table_id = msg.get("table_id")
    if table_id not in tables.keys():
        reply = {"error": "Table not found"}
        client.send(reply)
        return
    
    table = tables[table_id]
    error = table.new_player(client)
    
    if error:
        reply = {"error": error}
        client.send(reply)
        return    
    
    reply = {"table_info": table.get_table_info(client)}
    client.send(reply)
    
    broadcast_new_player(table.players)

    if table.is_full():
        table.state = "FULL"
        broadcast_state_change( table.players, "FULL" )
        

def create_table_handler (msg, client):
    table_id = get_new_table_id()
    new_table = Table(table_id)
    new_table.new_player(client)
    
    tables[table_id] = new_table

    reply = {"table_info": new_table.get_table_info(client)}
    client.send(reply)


def player_confirmation_handler (msg, client):
    table_id = msg.get("table_id")
    if table_id not in tables.keys():
        reply = {"error": "Table not found"}
        client.send(reply)
        return

    table = tables[table_id]
    error = table.confirm_player(client)
    
    if error:
        reply = {"error": error}
        client.send(reply)
        return
    
    pl_num = table.get_player_num( client )
    broadcast_player_confirmation( table.players, pl_num )
    
    if table.all_confirmed():
        broadcast_state_change(table.players, "SHUFFLE")
        deck = generate_deck()
        msg = {"data": { "deck": deck }}
        table.players[0].client.send(msg)
    

def relay_handler (msg, client):
    table_id = msg.get("table_id")
    if table_id not in tables.keys():
        reply = {"error": "Table not found"}
        client.send(reply)
        return
    
    #TODO: verify players
    #TODO: verify relays
    table = tables[ table_id ]
    relay_to = msg.get("relay_to")
    data = {"data": msg.get("data")}
    table.players[ relay_to ].client.send( data )
        

def deck_key_sharing_handler(msg, client):
    table_id = msg.get("table_id")
    if table_id not in tables.keys():
        reply = {"error": "Table not found"}
        client.send(reply)
        return
    
    table = tables[ table_id ]
    error = table.add_deck_key( client, msg.get("deck_key") )

    if error:
        reply = {"error": error}
        client.send(reply)
        return

    if table.all_deck_keys():
        broadcast_deck_keys(table.players)
        table.state = "BIT_COMMIT"


def bit_commit_handler( msg, client ):
    table_id = msg.get("table_id")
    if table_id not in tables.keys():
        reply = {"error": "Table not found"}
        client.send(reply)
        return

    table = tables[ table_id ]
    commit = msg.get("bit_commit")
    error = table.add_commit( client, commit )

    if error:
        reply = {"error": error}
        client.send(reply)
        return



#########################################################################
## Client functions
class Client:
    def __init__ (self, socket, name, sv_priv_key, sv_pub_key):
        self.socket = socket
        self.name = name
        self.pub_key = None
        self.sv_priv_key = sv_priv_key
        self.sv_pub_key = sv_pub_key

    def send (self, msg):
        msg = json.dumps(msg).encode().ljust(BUFFER_SIZE, b' ')
        #TODO: error handling
        try:
            self.socket.send(msg)
        except socket.error:
            print("This client is not connected!")


    def __eq__(self, other):
        if isinstance(other, Player):
            return self == other.client
        return self.socket == other.socket


#########################################################################
## Player functions
class Player:
    def __init__ (self, client, num):
        self.score = 0
        self.rounds_won = 0
        self.client = client        
        self.num = num
        self.confirmed = False
        self.commit = None

    def set_num (self, num):
        self.num = num

    def __eq__(self, other):
        return self.client == other


#########################################################################
## Table functions
class Table:
    def __init__ (self, table_id, title="Hearts"):
        self.table_id = table_id
        self.title = title
        self.max_player_count = 4
        self.state = "OPEN"
        self.players = []
        self.player_count = 0
        self.players_confirmed = 0
        self.deck_keys = 0
        self.commits = 0


    def new_player (self, client):
        if client in self.players:
            return "Already inside"
            
        if self.player_count >= self.max_player_count:
            return "Table is full"
        
        self.players.append(Player(client, self.player_count))
        self.player_count += 1
    
        return None
    

    def player_exists (self, client):
        return client in self.players
        
    
    def is_full(self):
        return self.player_count == self.max_player_count


    def all_confirmed(self):
        return self.players_confirmed == self.max_player_count


    def all_deck_keys(self):
        return self.deck_keys == self.max_player_count


    def all_commits(self):
        return self.commits == self.max_player_count


    def player_left (self, client):
        for p in self.players:
            p.confrimed = False
        self.players_confirmed = 0
        self.player_count -=1
        

    def get_table_info (self, client):
        return {
            "table_id": self.table_id,
            "title": self.title,
            "player_num": self.get_player_num(client),
            "players": self.get_players()
        }
        

    def get_player_num(self, client):
        return self.players.index(client)


    def get_player( self, client ):
        i = self.players.index(client)
        return self.players[i]


    def get_players(self):
        p_list = []
        for p in self.players:
            p_list.append({
                "name": p.client.name,
                "num": p.num,
                "pub_key": security.get_key_bytes( p.client.pub_key )
            })
        return p_list
        

    def confirm_player (self, client):
        if client not in self.players:
            return "Player is not in this table"
        
        if self.state != "FULL":
            return "Action not valid in current table state"

        player = self.get_player( client)
        if player.confirmed:
            return "Player already confirmed"
        
        player.confirmed = True
        self.players_confirmed += 1
        return None
        

    def add_deck_key( self, client, key ):
        if client not in self.players:
            return "Player is not in this table"

        if self.state != "SHUFFLING":
            return "Action not valid in current table state"

        player = self.get_player( client )
        if player.deck_key:
            return "Player already provided key"
        
        player.deck_key = key
        self.deck_keys += 1
        return None


    def add_commit( self, client, commit ):
        if client not in self.players:
            return "Player is not in this table"

        if self.state != "SHUFFLING":
            return "Action not valid in current table state"

        player = self.get_player( client )
        if player.deck_key:
            return "Player already provided key"

        player.commit = commit
        self.commits += 1

#########################################################################
## Main server functions

def redirect_messages (msg, client_socket):
    intent = msg.get("intent")
    
    # New client
    if intent == "register":
        register_client (msg, client_socket)

    # Registered client
    elif client_socket in clients.keys():
        client = clients[client_socket]
        
        if intent == "get_table_list":
            send_table_list (client)
    
        elif intent == "join_table":
            join_table_handler (msg, client)
                    
        elif intent == "create_table":
            create_table_handler (msg, client)
        
        elif intent == "confirm_players":
            player_confirmation_handler (msg, client)

        elif intent == "relay":
            relay_handler( msg, client )

        elif intent == "share_deck_key":
            deck_key_sharing_handler( msg, client )

        elif intent == "bit_commit":
            bit_commit_handler( msg, client )

        elif intent == "play":
            # making a play
            pass
        else:
            pass



print ("Starting table manager...")
sock.listen(1)
print ("Listening on port",SERVER_PORT,"\n")

read_list = [sock]

while True:
    readable, writable, errored = select.select (read_list, [], [])
    for s in readable:
        # New TCP connection
        if s is sock:
            client_socket, address = sock.accept()
            read_list.append( client_socket )
            pre_register_client( client_socket )
            send_pub_key( client_socket )
            print ("Connection from", address)
        # Client sent a message
        else:
            data = s.recv (BUFFER_SIZE).decode()
            if data:
                print ("Received:",data)
                msg = json.loads(data)
                redirect_messages (msg, s)
            else:
                print("Client has disconnected")
                s.close() #TODO: remover dos jogos, ou manter para quando reconecta?
                read_list.remove (s)
                
                
