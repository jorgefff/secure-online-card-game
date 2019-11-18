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
sock.bind(SV_ADDR)


def send_pub_key (client_socket):
    msg = {"pub_key" : sv_pub_key}
    msg = json.dumps(msg).encode()
    client_socket.send(msg)


def send_game_list (client_socket):
    game_list = []
    for game in games.values():
        if game.state == "OPEN":
            game_list.append({
                "id": game.game_id,
                "title": game.title,
                "player_count": game.player_count,
                "max_players": game.max_player_count})

    msg = {"get_game_list": game_list}
    client_socket.send(msg)


def register_client (msg, client_socket):
    name = msg.get("name")
    pub_key = msg.get("pub_key")
    new_client = Client (client_socket, name, pub_key)
    clients[client_socket] = new_client
    

def validate_player (action, game_id, player):
    pass


def join_game_handler (msg, client):
    game_id = msg.get("game_id")

    if game_id in games.keys():
        success, player_num, is_full, error = games[game_id].new_player(client)
    else:
        success = False
        error = "Game not found"

    if success:
        reply = {"join_game": player_num}
    else:
        reply = {"error": error}

    client.send(reply)    
    return success


def get_new_game_id():
    global game_id_counter
    new_id = game_id_counter
    game_id_counter += 1
    return new_id


def create_game_handler (msg, client):
    game_id = get_new_game_id()
    new_game = Game(game_id)
    new_game.new_player(client)
    games[game_id] = new_game

    reply = {"game_id": game_id}
    client.send(reply)


def player_confirmation_handler (msg, client):
    game_id = msg.get("game_id")
    
    if game_id in games.keys():
        success, error = games[game_id].confirm_player(client)
    else:
        success = False
        error = "Game not found"

    if not success:
        reply = {"confirm_players": "ok"}
    else:
        reply = {"error": error}

    client.send(reply)


def inform_of_player_confirmation (msg, client_socket):
    pass


def inform_of_new_player (game_id):
    game = games[game_id]
    new_player = game.players[-1].client.name
    for p in game.players[:-1]:
        msg = {
            "game_update": {
                "update": "new_player", 
                "new_player": new_player}}
        
        p.client.send(msg)


class Client:
    def __init__ (self, socket, name, pub_key):
        self.socket = socket
        self.name = name
        self.pub_key = pub_key
        self.sv_pub_key = sv_pub_key # if theres a unique sv_pub_key per client

    def send (self, msg):
        msg = json.dumps(msg).encode()
        #TODO: error handling
        self.socket.send(msg)


    def __eq__(self, other):
        if isinstance(other, Player):
            return self == other.client
        return self.socket == other.socket


class Player:
    def __init__ (self, client):
        self.score = 0
        self.rounds_won = 0
        self.client = client        
    
    def __eq__(self, other):
        return self.client == other


class Game:
    def __init__ (self, game_id):
        self.game_id = game_id
        self.title = "Hearts"
        self.max_player_count = 4
        self.state = "OPEN"
        self.players = []
        self.player_count = 0


    def new_player (self, client):
        if client in self.players:
            error = "Already inside"
            return False, 0, True, error
            
        if self.player_count >= self.max_player_count:
            error = "Game is full"
            return False, 0, True, error
        
        self.players.append(Player(client))
        self.player_count += 1
        is_full = (self.player_count == self.max_player_count)
        return True, self.player_count, is_full, None
    

    def player_left (self, player):
        #TODO
        pass


    def confirm_player (self, player):
        #TODO: verify: player is inside & game.status
        pass


def redirect_messages (msg, client_socket):
    intent = msg.get("intent")
    
    if intent == "register":
        # New client
        register_client (msg, client_socket)

    elif client_socket in clients.keys():
        # Registered client
        client = clients[client_socket]
        
        if intent == "get_game_list":
            send_game_list (client)
    
        elif intent == "join_game":
            success = join_game_handler (msg, client)
            if success:
                inform_of_new_player (msg.get("game_id"))

        elif intent == "create_game":
            create_game_handler (msg, client)
        
        elif intent == "confirm_players":
            success = player_confirmation_handler (msg, client)
            if success:
                inform_of_player_confirmation (msg, client)
            #TODO: if 4 players confirmed: game.state = "SHUFFLING"
            pass
            
        elif intent == "?":
            # shuffling
            #   proxying deck
            # commiting deck
            pass
        
        elif intent == "play":
            # making a play
            pass
        else:
            pass



print ("Starting table manager...")
sock.listen(1)
print ("Listening on port",SERVER_PORT,"\n")

read_list = [sock, sys.stdin]

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
                s.close()
                read_list.remove (s)
        
                
