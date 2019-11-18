import socket
import json
import time
import datetime
import base64
import os
from sys import argv
import sys
import select

# Select port
if len(argv) != 2:
    print ("usage: python3 player_client.py <PORT_NUMBER>")
    exit()
if not argv[1].isdigit:
    print ("Port argument needs to be an integer")
    exit()
if int(argv[1]) < 1:
    print ("port number needs to be > 0")
    exit()




# Constants
IP = "localhost"
PORT = int(argv[1])
SERVER_PORT = 50000
CLIENT_PORT = PORT

# User info
client_name = "nome"+str(PORT)+"blabla" # placeholder, should be read from CC reader

# Clear ports
#os.system("kill -9 $(lsof -t -i:" + str(CLIENT_PORT) + ")")
#time.sleep(1)
#print("\n")
#sudo netstat -ap | grep 50000
#lsof -t -i:50000
#lsof -t -i:50001
#fuser -k 50001/tcp


# Addresses
SV_ADDR = (IP, SERVER_PORT)
CLIENT_ADDR = (IP, CLIENT_PORT)

# Socket configs
BUFFER_SIZE = 1024

# TCP Socket
sock = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
sock.bind (CLIENT_ADDR)

# Global vars
PUB_KEY = "PLACEHOLDER_PUBK"
PRIV_KEY = "PLACEHOLDER_PRIVK"
sv_pub_key = "PLACEHOLDER_SV_PUBK"


#########################################################################
## Auxiliary functions

def print_client_options():
    print ()
    print ("---------------------------------")
    print ("1 - Connect to server")
    print ("2 - List games")
    print ("3 - Join game")
    print ("4 - Create game")
    print ()
    print ("0 - Exit")
    print ("---------------------------------")
    print ()


def wait_for_reply (expected):
    received, addr = sock.recvfrom (BUFFER_SIZE)
    print ("\nReceived:", received)
    
    if not received:
        print("Server side error!\nClosing client")
        sock.close()
        exit()
        
    reply = received.decode()
    reply = json.loads(reply)
    
    if "error" in reply.keys():
        print ("ERROR:", reply.get("error"))
        sock.close()
        exit()

    return reply.get(expected)
    

def wait_for_reply_or_input (expected_reply):
    read_list = [sock, sys.stdin]
    while True:
        readable, writable, errored = select.select (read_list, [], [])
        for s in readable:
            if sys.stdin in readable:
                cmd = sys.stdin.readline()
                if cmd:
                    print(">>>>",cmd)
            else:
                reply = s.recv (BUFFER_SIZE).decode()
                reply = msg = json.loads(reply)
                if "error" in reply.keys():
                    print ("ERROR:", reply.get("error"))
                    s.close()
                    exit()
                return msg.get(expected_reply)


def register_to_server():
    msg = {
        "intent": "register",
        "name": client_name,
        "pub_key": PUB_KEY}
    msg = json.dumps(msg).encode()
    sock.send(msg)
    

def format_game_list (game_list):
    # Formats the game list from JSON
    if not game_list:
        return ["No games available"]

    new_list = []
    for g in game_list:
        id              = str(g.get("id"))
        title           = str(g.get("title"))
        player_count    = str(g.get("player_count"))
        max_players     = str(g.get("max_players"))
        line = id+" - "+title+" - ["+player_count+"/"+max_players+"]"
        new_list.append(line)

    return new_list


def print_game_state (game):
    if game.state == "OPEN":
        pass
    pass


def request_game_list():
    request = {"intent" : "get_game_list"}
    request = json.dumps(request).encode()
    sock.sendto(request, SV_ADDR)


def request_to_join_game (id):
    request = {
        "intent" : "join_game",
        "game_id" : id}
    request = json.dumps(request).encode()
    sock.sendto(request, SV_ADDR)


def request_to_create_game():
    request = {"intent" : "create_game"}
    request = json.dumps(request).encode()
    sock.sendto(request, SV_ADDR)

#########################################################################
## Player class

class Player:
    def __init__ (self):
        self.name = ""
        self.pub_key = ""
        self.deck_key = ""
        self.num = 0
        self.score = 0
        self.rounds_won = 0
        self.confirmed = False

#########################################################################
## Game class

class Game:
    def __init__ (self, game_id, player_num=1):
        self.players_inside = player_num
        self.num = player_num
        self.game_id = game_id
        self.state = "OPEN"
        self.other_players = []

    def wait_in_lobby (self):
        # Wait for players to join the lobby
        while True:
            print_game_state(self)
            wait_for_reply_or_input("game_update")


    def comfirm_players (self):
        # Lobby is full - confirm you want to play
        # Wait for confirmation of others
        # Begin shuffling process
        pass

    def shuffling (self):
        # 5% chance to take a card
        # if no card taken:
        #   Swap / or not
        # Shuffle
        # Pass the cards
        # Bit commit        
        pass

    def commit_deck (self):
        # Hash deck
        pass

    def start_game (self):
        if self.num == 1:
            self.make_play(self)
        else:
            self.wait_for_play(self)
    
    def make_play (self):
        pass

    def wait_for_play (self):
        pass

        
#########################################################################
## Client functions

class Client:
    def __init__ (self):
        pass

    def join_server (self):
        # Makes TCP connection to server
        try:
            sock.connect (SV_ADDR)
        except:
            print ("Connection failed")
            return
        sv_pub_key = wait_for_reply ("pub_key")
        register_to_server()
        

    def list_games (self):
        # Lists available games
        request_game_list()
        game_list = wait_for_reply ("get_game_list")
        fmtd_game_list = format_game_list (game_list)
        print ("Games:")
        for game in fmtd_game_list:
            print ("   "+game)


    def join_game (self):
        # Joins selected game
        while True:
            try:
                game_id = int(input("Game number: "))
                break
            except:
                print("Not a number!")
        request_to_join_game (game_id)
        player_num = wait_for_reply ("player_num")
        game = Game (game_id, player_num)
        game.wait_in_lobby()
    

    def create_game (self):
        # Creates a new game
        request_to_create_game()
        game_id = wait_for_reply ("game_id")
        game = Game (game_id)
        game.wait_in_lobby()


    def close (self):
        sock.close()
        exit()


    def decision_loop (self):
        # Ask player what he wants to do
        opts = [self.close, self.join_server, self.list_games, self.join_game, self.create_game]
        while (True):
            print_client_options()
            opt = input("> ")
            if opt.isdigit() and int(opt) >= 0 and int(opt) < len(opts):
                opts [int(opt)]()
                print()


if __name__ == "__main__":
    print ("Starting client")
    c = Client()
    try:
        c.decision_loop()
    except socket.error:
        sock.close()



