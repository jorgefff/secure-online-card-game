import socket 
import json
import select
import time
import datetime
import base64
import os
from sys import argv
import sys

# Global vars
sv_pub_key = "placeholdersvkey"
game_id_counter = 0
games = {}
clients = {}

# Address
IP = "localhost"
SERVER_PORT = 50000
SV_ADDR = (IP, SERVER_PORT)

# Socket configs
BUFFER_SIZE = 1024

# TCP Socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(SV_ADDR)


def send_pub_key( client_socket ):
    msg = {"pub_key" : sv_pub_key}
    msg = json.dumps(msg).encode().ljust(BUFFER_SIZE, b' ')
    client_socket.send(msg)


def send_game_list( client_socket ):
    game_list = []
    for game in games.values():
        if game.state == "OPEN":
            game_list.append({
                "id": game.game_id,
                "title": game.title,
                "player_count": game.player_count,
                "max_players": game.max_player_count})

    msg = {"game_list": game_list}
    client_socket.send(msg)


def register_client( msg, client_socket ):
    name = msg.get("name")
    pub_key = msg.get("pub_key")
    new_client = Client (client_socket, name, pub_key)
    clients[client_socket] = new_client


def get_new_game_id():
    global game_id_counter
    new_id = game_id_counter
    game_id_counter += 1
    return new_id

    
def broadcast_new_player( players ):
    player = players[-1]
    new_player = {
        "name": player.client.name,
        "pub_key": player.client.pub_key,
        "num": player.num}

    for p in players[:-1]:
        msg = {
            "game_update": {
                "update": "new_player", 
                "new_player": new_player}}
        p.client.send(msg)


def broadcast_player_confirmation( players, pl_num ):
    for p in players:
        msg = {
            "game_update": {
                "update": "player_confirmation", 
                "player_num": pl_num}}
        p.client.send(msg)


def broadcast_state_change( players, new_state ):
    for p in players:
        msg = {
            "game_update": {
                "update": "game_state", 
                "game_state": new_state}}
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



def join_game_handler (msg, client):
    game_id = msg.get("game_id")
    if game_id not in games.keys():
        reply = {"error": "Game not found"}
        client.send(reply)
        return
    
    game = games[game_id]
    error = game.new_player(client)
    
    if error:
        reply = {"error": error}
        client.send(reply)
        return    
    
    reply = {"game_info": game.get_game_info(client)}
    client.send(reply)
    
    broadcast_new_player(game.players)

    if game.is_full():
        game.state = "FULL"
        broadcast_state_change( game.players, "FULL" )
        

def create_game_handler (msg, client):
    game_id = get_new_game_id()
    new_game = Game(game_id)
    new_game.new_player(client)
    
    games[game_id] = new_game

    reply = {"game_info": new_game.get_game_info(client)}
    client.send(reply)


def player_confirmation_handler (msg, client):
    game_id = msg.get("game_id")
    if game_id not in games.keys():
        reply = {"error": "Game not found"}
        client.send(reply)
        return

    game = games[game_id]
    error = game.confirm_player(client)
    
    if error:
        reply = {"error": error}
        client.send(reply)
        return
    
    pl_num = game.get_player_num( client )
    broadcast_player_confirmation( game.players, pl_num )
    
    if game.all_confirmed():
        broadcast_state_change(game.players, "SHUFFLE")
        deck = generate_deck()
        msg = {"data": { "deck": deck }}
        game.players[0].client.send(msg)
    

def relay_handler (msg, client):
    game_id = msg.get("game_id")
    if game_id not in games.keys():
        reply = {"error": "Game not found"}
        client.send(reply)
        return
    
    #TODO: verify players
    #TODO: verify relays
    game = games[ game_id ]
    relay_to = msg.get("relay_to")
    data = {"data": msg.get("data")}
    game.players[ relay_to ].client.send( data )
        

def deck_key_sharing_handler(msg, client):
    game_id = msg.get("game_id")
    if game_id not in games.keys():
        reply = {"error": "Game not found"}
        client.send(reply)
        return
    
    game = games[ game_id ]
    error = game.add_deck_key( client, msg.get("deck_key") )

    if error:
        reply = {"error": error}
        client.send(reply)
        return

    if game.all_deck_keys():
        broadcast_deck_keys(game.players)
        game.state = "BIT_COMMIT"


def bit_commit_handler( msg, client ):
    game_id = msg.get("game_id")
    if game_id not in games.keys():
        reply = {"error": "Game not found"}
        client.send(reply)
        return

    game = games[ game_id ]
    commit = msg.get("bit_commit")
    error = game.add_commit( client, commit )

    if error:
        reply = {"error": error}
        client.send(reply)
        return



#########################################################################
## Client functions
class Client:
    def __init__ (self, socket, name, pub_key):
        self.socket = socket
        self.name = name
        self.pub_key = pub_key
        self.sv_pub_key = sv_pub_key # if theres a unique sv_pub_key per client

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
## Game functions
class Game:
    def __init__ (self, game_id, title="Hearts"):
        self.game_id = game_id
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
            return "Game is full"
        
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
        

    def get_game_info (self, client):
        return {
            "game_id": self.game_id,
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
                "pub_key": p.client.pub_key})
        return p_list
        

    def confirm_player (self, client):
        if client not in self.players:
            return "Player is not in this game"
        
        if self.state != "FULL":
            return "Action not valid in current game state"

        player = self.get_player( client)
        if player.confirmed:
            return "Player already confirmed"
        
        player.confirmed = True
        self.players_confirmed += 1
        return None
        

    def add_deck_key( self, client, key ):
        if client not in self.players:
            return "Player is not in this game"

        if self.state != "SHUFFLING":
            return "Action not valid in current game state"

        player = self.get_player( client )
        if player.deck_key:
            return "Player already provided key"
        
        player.deck_key = key
        self.deck_keys += 1
        return None


    def add_commit( self, client, commit ):
        if client not in self.players:
            return "Player is not in this game"

        if self.state != "SHUFFLING":
            return "Action not valid in current game state"

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
        
        if intent == "get_game_list":
            send_game_list (client)
    
        elif intent == "join_game":
            join_game_handler (msg, client)
                    
        elif intent == "create_game":
            create_game_handler (msg, client)
        
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
            read_list.append (client_socket)
            send_pub_key (client_socket)
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
                
                
