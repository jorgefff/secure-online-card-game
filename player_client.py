import socket
import json
import time
import datetime
import base64
import os
from sys import argv
import sys
import select
import random as rand

# Select port
AUTO = False
AUTO_PORTS = [52001,52002,52003,52004]
if len(argv) < 2:
    print ("usages:")
    print("python3 player_client.py <PORT_NUMBER>")
    print("python3 player_client.py AUTO <1-4>")
    exit()
if argv[1].lower() == "auto":
    if not argv[2].isdigit:
        print("python3 player_client.py AUTO <1-4>")
        exit()
    AUTO = True
elif not argv[1].isdigit:
    print ("Port argument needs to be an integer")
    exit()
elif int(argv[1]) < 1:
    print ("port number needs to be > 0")
    exit()




# Address constants
IP = "localhost"
if AUTO:
    PORT = AUTO_PORTS[int(argv[2])]
else:
    PORT = int(argv[1])
SERVER_PORT = 50000
CLIENT_PORT = PORT

# Chances
PICK_CHANCE = 0.05
SWAP_CHANCE = 0.5
COMMIT_CHANCE = 0.5

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
sock = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
sock.setsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR, 1 )
sock.bind( CLIENT_ADDR )

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

def decide_to_pick():
    return rand.random() < PICK_CHANCE

def decide_to_swap():
    return rand.random() < SWAP_CHANCE

def decide_to_commit():
    return rand.random() < COMMIT_CHANCE

# Requests the list of open games
def request_game_list():
    request = {"intent" : "get_game_list"}
    request = json.dumps(request).encode()
    sock.send(request)


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
    sock.send(request)


# Requests to create a new game
def request_to_create_game():
    request = {"intent" : "create_game"}
    request = json.dumps(request).encode()
    sock.send(request)


# Confirm you want to play with these players
def send_pl_confirmation (game_id):
    #TODO: 
    # "The croupier will only start the game after getting a signed statement
    # from all players including the identity of the opponents"
    msg = {
        "intent": "confirm_players",
        "game_id": game_id}
    msg = json.dumps(msg).encode()
    sock.send(msg)


# Waits for a reply from server (blocking)
def wait_for_reply (expected_reply=None):
    received, addr = sock.recvfrom (BUFFER_SIZE)
    
    if not received:
        print("Server side error!\nClosing client")
        sock.close()
        exit()
        
    reply = received.decode().rstrip()
    print ("\nReceived:", received)
    reply = json.loads(reply)
    
    if "error" in reply.keys():
        print ("ERROR:", reply[ "error" ])
        sock.close()
        exit()

    if expected_reply:
        return reply.get(expected_reply)
    return reply
    

# Waits for either a server reply or user input (non blocking)
def wait_for_reply_or_input (expected_reply=None):
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
                reply = s.recv (BUFFER_SIZE).decode().rstrip()
                print( "Received:", reply )
                reply = json.loads(reply)
                if "error" in reply.keys():
                    print ("ERROR:", msg.get("error"))
                    s.close()
                    exit()
                if expected_reply:
                    return reply.get(expected_reply), None
                return reply, None


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


# Get next player
def next_player( game ):
    idx = game.player_num + 1
    if idx == game.max_players:
        idx = 0
    player = game.players[idx]
    return player


# Get previous player
def prev_player(game):
    pass


# Returns a random player
def random_player(game):
    options = [0, 1, 2, 3]
    options.remove( game.player_num )
    rand_num = rand.choice( options )
    return game.players[ rand_num ]



# Shows the current state of the game
def print_lobby_state (game):
    if game.state == "OPEN":
        print("\n\n\n\n\n------------------")
        print("Players:")
        for p in game.players:
            print(p.num+1, "-", p.name)
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
            print(p.num+1, "-", p.name," - Confirmed:",confirmed)
        print("\n")
        print("Commands: confirm, exit")


def encrypt_cards( deck, key=None ):
    #TODO
    # If None, use own key
    # Else use key
    return deck

def bit_commit( deck ):
    #TODO
    return "BIT-COMMIT"


def decrypt_cards( deck ):
    #TODO
    return deck




def relay_data (game, data, send_to="next"):
    if send_to == "random":
        next_p = random_player( game )
    else:
        next_p = next_player( game )

    msg = {
        "intent": "relay",
        "game_id": game.game_id,
        "relay_to": next_p.num,
        "data": data}

    msg = json.dumps(msg).encode()
    sock.send(msg)


    
        

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
        self.player_num = info.get("player_num")
        self.deck = []
        self.passing_data = {"commits": {}, "deck_keys": {}}
        self.deck_key = "deck_key-TODO"
        self.state = "OPEN"
        self.players = [
            Player(
                p.get("num"),
                p.get("name"),
                p.get("pub_key")) 
            for p in info.get("players")]
        self.pl_count = len(self.players)
        self.max_players = 4
        

    def start(self):
        self.wait_in_lobby()
        self.deck_encrypthing()
        self.card_selection()
        self.commit_deck()
        self.share_deck_key()
        self.verify_equal_info()
        self.decrypt_deck()
        self.start_game()


    def update_state (self, new_state):
        self.state = new_state
        global game_cmds
        if new_state == "OPEN":
            game_cmds = ["exit"]
        elif new_state == "FULL":
            game_cmds = ["exit", "confirm"]
        else:
            game_cmds = []


    def new_player (self, player):
        new_player = Player(
            player.get("num"),
            player.get("name"),
            player.get("pub_key"))
        self.players.append(new_player)
        self.pl_count = len(self.players)
    

    def player_left (self, p_num):
        self.players.pop(p_num)
        self.pl_count = len(self.players)
        for i in range(p_num, self.pl_count):
            self.players[i].num = i
            

    def player_confirmed (self, player_num):
        self.players[ player_num ].confirmed = True


    def wait_in_lobby( self ):
        # Wait for players to join the lobby
        AUTO_ONCE = True
        while self.state in ["OPEN", "FULL"]:
            # Automatically send confirmation once
            if AUTO and AUTO_ONCE and self.state == "FULL":
                time.sleep(rand.randrange(1,3))
                send_pl_confirmation(self.game_id)
                AUTO_ONCE = False

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
        

    def deck_encrypthing( self ):
        reply = wait_for_reply( "data" )
        deck = reply.get( "deck" )
        encrypt_cards( deck )
        rand.shuffle( deck )
        data = { "deck": deck }
        relay_data( self, data )


    def card_selection( self ):
        while True:
            
            reply = wait_for_reply( "data" )

            # Someone started bit commit process
            if "commits" in reply.keys():
                commits = reply.get( "commits" )
                self.passing_data[ "commits" ].update( commits )
                break
            
            deck_passing = reply.get( "deck" ) 
            passing_size = len( deck_passing )
            deck_size = len( self.deck )

            # The passing deck is empty - decide if start commit process
            if passing_size == 0 and decide_to_commit():
                break
            
            # Pick one
            elif deck_size < 13 and decide_to_pick():    
                pick = rand.randrange( 0, passing_size )
                card = deck_passing.pop( pick )
                self.deck.append( card )
            # Swap cards
            elif deck_size > 0 and decide_to_swap():
                max_swaps = min( deck_size, passing_size )

            # Shuffle
            if passing_size > 0:
                rand.shuffle( deck_passing )
            
            # Send to random player
            data = {"deck": deck_passing }
            relay_data( self, data, "random" )


    def commit_deck( self ):
        commit = bit_commit( self.deck )
        my_commit = { str( self.player_num ): commit }
        self.passing_data[ "commits" ].update( my_commit )
        relay_data( self, self.passing_data )

        while len( self.passing_data[ "commits" ] ) < 4:
            data = wait_for_reply( "data" )
            commits = data[ "commits" ]
            self.passing_data[ "commits" ].update( commits )
            relay_data( self, self.passing_data )

        #TODO: Verify commits


    def share_deck_key( self ):
        my_key = { str( self.player_num ) : self.deck_key }
        self.passing_data[ "deck_keys" ].update( my_key )
        relay_data( self, self.passing_data )

        while len( self.passing_data[ "deck_keys" ] ) < 4:
            data = wait_for_reply( "data" )
            deck_keys = data[ "deck_keys" ]
            self.passing_data[ "deck_keys" ].update( deck_keys )
            relay_data( self, self.passing_data )


    def verify_equal_info( self ):
        # Send passing_data to server to check if everyone has equal info
        pass


    def decrypt_deck( self ):
        #TODO
        pass
        # for i in range(0, self.pl_count):
        #     idx = self.pl_count - 1 - i
        #     key = self.players[ idx ].pub_key
        #     decrypt_cards( self.deck, key )


    def start_game(self):
        print("\n\n\n\n\n")
        for d in self.passing_data:
            print( self.passing_data[d] )
        exit()
        
        print("The game is starting!")
        while True:
            time.sleep(1)

#########################################################################
## Client functions

class Client:
    def __init__( self ):
        pass

    def join_server( self ):
        try:
            sock.connect (SV_ADDR)
        except:
            print ("Connection failed")
            return
        reply = wait_for_reply ()
        sv_pub_key = reply.get("pub_key")
        register_to_server()
    
    
    def list_games( self ):
        request_game_list()
        reply = wait_for_reply ()
        game_list = reply.get("game_list")
        fmtd_game_list = format_game_list (game_list)
        print ("Games:")
        for game in fmtd_game_list:
            print ("   "+game)


    def join_game (self,game_id=None):
        if game_id == None:
            while True:
                try:
                    game_id = int(input("Game number: "))
                    break
                except:
                    print("Not a number!")
        request_to_join_game (game_id)
        game_info = wait_for_reply ("game_info")
        game = Game(game_info)
        game.start()


    def create_game( self ):
        request_to_create_game()
        game_info = wait_for_reply ("game_info")
        game = Game(game_info)
        game.start()


    def close( self ):
        sock.close()
        exit()

    
    def decision_loop( self ):
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


def automatic_main():
    print("Starting automatic client")
    c = Client()
    print("Connecting...")
    c.join_server()
    time.sleep(1)
    
    if PORT == AUTO_PORTS[0]:
        print("\nCreating game")
        c.create_game()
    else:
        time.sleep(1)
        c.list_games()
        print("Joining game")
        time.sleep(3)
        c.join_game(0)


if __name__ == "__main__":
    if AUTO:
        automatic_main()
    else:
        main()
