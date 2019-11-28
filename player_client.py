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
client_name = "nome_"+str(PORT)[-1]+" blabla" # placeholder, should be read from CC reader

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

# Commands available at the current state of the game
game_cmds = ["exit"]

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

# Requests the list of open games
def request_game_list():
    request = {"intent" : "get_game_list"}
    request = json.dumps(request).encode()
    sock.sendto(request, SV_ADDR)


# Registers on the server
def register_to_server():
    msg = {
        "intent": "register",
        "name": client_name,
        "pub_key": PUB_KEY}
    msg = json.dumps(msg).encode()
    sock.send(msg)


# Requests to join an open game
def request_to_join_game (id):
    request = {
        "intent" : "join_game",
        "game_id" : id}
    request = json.dumps(request).encode()
    sock.sendto(request, SV_ADDR)


# Requests to create a new game
def request_to_create_game():
    request = {"intent" : "create_game"}
    request = json.dumps(request).encode()
    sock.sendto(request, SV_ADDR)


# Confirm you want to play with these players
def send_pl_confirmation (game_id):
    #TODO: 
    # "The croupier will only start the game after getting a signed statement
    # from all players including the identity of the opponents"
    msg = {
        "intent": "confirm_players",
        "game_id": game_id}
    msg = json.dumps(msg).encode()
    sock.sendto(msg, SV_ADDR)


# Waits for a reply from server (blocking)
def wait_for_reply (expected):
    received, addr = sock.recvfrom (BUFFER_SIZE)
    print ("\nReceived:", received)#DEBUG
    
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
    

# Waits for either a server reply or user input (non blocking)
def wait_for_reply_or_input (expected_reply):
    read_list = [sock, sys.stdin]
    while True:
        readable, writable, errored = select.select (read_list, [], [])
        for s in readable:
            if sys.stdin in readable:
                cmd = sys.stdin.readline()
                if cmd:
                    cmd = cmd.strip().lower()
                    if cmd in game_cmds:
                        return None, cmd
                    else:
                        print ("Invalid command!")
            else:
                reply = s.recv (BUFFER_SIZE).decode()
                reply = msg = json.loads(reply)
                if "error" in reply.keys():
                    print ("ERROR:", reply.get("error"))
                    s.close()
                    exit()
                return msg.get(expected_reply), None


# Formats the game list from JSON to readable data
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


# Converts the received (JSON) player to Player object
def json_to_player(msg):
    return Player(
        msg.get("num"),
        msg.get("name"),
        msg.get("pub_key"))


# Converts the received (JSON) player list to a list of Player objects
def json_to_player_lst(p_list):
    return [
        Player(
            p.get("num"),
            p.get("name"),
            p.get("pub_key")
        ) for p in p_list]


# Shows the current state of the game
def print_lobby_state (game):
    if game.state == "OPEN":
        print("\n\n\n\n\n------------------")
        print("Players:")
        for p in game.players:
            print(p.num, "-", p.name)
        print("\n")
        print("Commands: exit")

    elif game.state == "FULL":
        print("\n\n\n\n\n------------------")
        print("Players:")
        for p in game.players:
            if p.confirmed:
                confirmed = "Yes"
            else:
                confirmed = "No"
            print(p.num, "-", p.name," - Confirmed:",confirmed)
        print("\n")
        print("Commands: confirm, exit")


        
        
#########################################################################
## Card class

class Card:
    def __init__(self):
        pass        


#########################################################################
## Deck class

class Deck:
    def __init__(self):
        pass


#########################################################################
## Player class

class Player:
    def __init__ (self, num, name, pub_key):
        self.num = num
        self.name = name
        self.pub_key = pub_key
        self.deck_key = None
        self.score = 0
        self.rounds_won = 0
        self.confirmed = False

    def set_num (self, num):
        self.num = num

#########################################################################
## Game class

class Game:
    def __init__ (self, info):
        self.game_id = info.get("game_id")
        self.title = info.get("title")
        self.num = info.get("num")
        self.state = "OPEN"
        self.players = json_to_player_lst(info.get("players"))
        self.players_inside = len(self.players)
        self.max_players = 4

    def start(self):
        self.wait_in_lobby()
        self.deck_encrypthing()
        self.card_selection()
        self.commit_deck()
        self.start_game()

    def update_state (self, state):
        self.state = state
        if state == "OPEN":
            game_cmds = ["exit"]
        elif state == "FULL":
            game_cmds = ["exit", "confirm"]
        else:
            game_cmds = []

    def new_player (self, player):
        new_player = json_to_player(player)
        self.players.append(new_player)
        self.players_inside = len(self.players)
    

    def player_left (self, player_num):
        # Remove player that left
        # Sort
        self.players_inside = len(self.players)


    def player_confirmed (self, player_num):
        self.players[player_num - 1].confirmed = True


    def wait_in_lobby (self):
        # Wait for players to join the lobby
        while self.state in ["OPEN","FULL"]:
        
            print_lobby_state(self)
            msg, cmd = wait_for_reply_or_input("game_update")
        
            # Received a message from server
            if msg:
                update = msg.get("update")
                if update  == "new_player":
                    self.new_player(msg.get("new_player"))

                elif update == "player_confirmation":
                    self.player_confirmed(msg.get("player_num"))

                elif update == "player_left":
                    self.player_left(msg.get("player_num"))

                elif update == "game_state":
                    self.update_state(msg.get("game_state"))

            # User input
            elif cmd:
                if cmd == "confirm":
                    send_pl_confirmation(self.game_id)
                elif cmd == "exit":
                    #TODO: request to exit game and not close socket / client
                    sock.close()
                    exit()
        

    def deck_encrypthing (self):
        # If player_1: receive from croupier
        # else wait for player_deck
        # pass deck
        pass

    def card_selection(self):
        # 5% chance to take a card
        # if no card taken:
        #   Swap / or not
        # Shuffle
        # Pass the cards
        pass

    def commit_deck (self):
        # Hash deck
        pass


        
#########################################################################
## Client functions

class Client:
    def __init__ (self):
        pass

    def join_server (self):
        try:
            sock.connect (SV_ADDR)
        except:
            print ("Connection failed")
            return
        sv_pub_key = wait_for_reply ("pub_key")
        register_to_server()
    
    
    def list_games (self):
        request_game_list()
        game_list = wait_for_reply ("get_game_list")
        fmtd_game_list = format_game_list (game_list)
        print ("Games:")
        for game in fmtd_game_list:
            print ("   "+game)


    def join_game (self):
        while True:
            try:
                game_id = int(input("Game number: "))
                break
            except:
                print("Not a number!")
        request_to_join_game (game_id)
        game_info = wait_for_reply ("game_info")
        game = Game(game_info)
        game.wait_in_lobby()


    def create_game (self):
        request_to_create_game()
        game_info = wait_for_reply ("game_info")
        game = Game(game_info)
        game.wait_in_lobby()


    def close (self):
        sock.close()
        exit()

    
    def decision_loop (self):
        opts = [self.close, self.join_server, self.list_games, self.join_game, self.create_game]
        while (True):
            print_client_options()
            opt = input("> ")
            if opt.isdigit() and int(opt) >= 0 and int(opt) < len(opts):
                opts [int(opt)]()
                print()



def main():
    print ("Starting client")
    c = Client()
    try:
        c.decision_loop()
    except socket.error:
        sock.close()

if __name__ == "__main__":
    main()
