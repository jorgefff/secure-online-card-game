import socket
import json
import time
import datetime
from base64 import b64decode, b64encode
import os
from sys import argv
import sys
import select
import random as rand
from client_modules.player import Player
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import security
# Chances
PICK_CHANCE = 0.05
SWAP_CHANCE = 0.5
COMMIT_CHANCE = 0.5


def decide_to_pick():
    return rand.random() < PICK_CHANCE

def decide_to_swap():
    return rand.random() < SWAP_CHANCE

def decide_to_commit():
    return rand.random() < COMMIT_CHANCE


# Get next player
def next_player( table ):
    idx = table.player_num + 1
    if idx == table.max_players:
        idx = 0
    player = table.players[idx]
    return player


# Returns a random player
def random_player(table):
    options = [0, 1, 2, 3]
    options.remove( table.player_num )
    rand_num = rand.choice( options )
    return table.players[ rand_num ]


# Shows the current state of the table
def print_lobby_state( table):
    if table.state == "OPEN":
        print("\n\n\n\n\n------------------")
        print("Players:")
        for p in table.players:
            print(p.num+1, "-", p.name)
        print("\n")
        print("Commands: exit")

    elif table.state == "FULL":
        print("\n\n\n\n\n------------------")
        print("Players:")
        for p in table.players:
            if p.confirmed:
                confirmed = "Yes"
            else:
                confirmed = "No"
            print(p.num+1, "-", p.name," - Confirmed:",confirmed)
        print("\n")
        print("Commands: confirm, exit")


def bit_commit( deck ):
    #TODO
    return "BIT-COMMIT"


def decrypt_cards( deck ):
    #TODO
    return deck


#########################################################################
## Table class
class Table:
    def __init__( self, client, table_id, title, player_num, players, auto=False):
        self.auto = auto
        self.table_cmds = ["exit"]
        self.table_id = table_id
        self.title = title
        self.player_num = player_num
        self.deck = []
        self.passing_data = {"commits": {}, "deck_keys": {}}
        self.priv_deck_key = None
        self.pub_deck_key = None
        self.state = "OPEN"
        self.players = players
        self.pl_count = len(self.players)
        self.max_players = 4
        self.c = client


    def start(self):
        self.wait_in_lobby()
        # Cycle:
        self.deck_encrypting()
        self.card_selection()
        self.commit_deck()
        self.share_deck_key()
        self.verify_equal_info()
        self.update_player_info()
        self.decrypt_deck()
        self.start_game()


    def update_state( self, new_state):
        self.state = new_state
        if new_state == "OPEN":
            self.table_cmds = ["exit"]
        elif new_state == "FULL":
            self.table_cmds = ["exit", "confirm"]
        else:
            self.table_cmds = []


    def new_player( self, player):
        new_player = Player(
            player.get("num"),
            player.get("name"),
            player.get("pub_key"))
        self.players.append(new_player)
        self.pl_count = len(self.players)
    

    def player_left( self, p_num):
        self.players.pop(p_num)
        self.pl_count = len(self.players)
        for i in range(p_num, self.pl_count):
            self.players[i].num = i
            

    def player_confirmed( self, player_num):
        self.players[ player_num ].confirmed = True


    def wait_in_lobby( self ):
        # Wait for players to join the lobby
        auto_once = True
        while self.state in ["OPEN", "FULL"]:
            
            # Auto-mode: automatically send confirmation when lobby is full
            if self.auto and auto_once and self.state == "FULL":
                time.sleep(rand.randrange(1,3))
                self.c.send_pl_confirmation(self.table_id)
                auto_once = False

            print_lobby_state(self)
            msg, cmd = self.c.wait_for_reply_or_input("table_update", self.table_cmds)
        
            # Received a message from server
            if msg:
                update = msg.get("update")
                if update  == "new_player":
                    self.new_player(msg.get("new_player"))

                elif update == "player_confirmation":
                    self.player_confirmed(msg.get("player_num"))

                elif update == "player_left":
                    self.player_left(msg.get("player_num"))

                elif update == "table_state":
                    self.update_state(msg.get("table_state"))

            # User input
            elif cmd:
                if cmd == "confirm":
                    self.c.send_pl_confirmation( self.table_id )
                elif cmd == "exit":
                    #TODO: request to exit table and not close socket / client
                    exit()
        

    def deck_encrypting( self ):
        reply = self.c.wait_for_reply( "data" )
        deck = reply.get( "deck" )
        # Generate password and IV
        self.deck_pwd = os.urandom(32)
        self.deck_iv = os.urandom(16)
        # Cipher each card        
        for i in range(0, len(deck)):
            deck[i] = security.AES_encrypt(
                pwd=self.deck_pwd,
                iv=self.deck_iv,
                text=deck[i]
            ).decode("utf-8")
        # Shuffle and relay
        rand.shuffle( deck )
        data = { "deck": deck }
        self.c.relay_data( self.table_id, data, next_player(self) )


    def card_selection( self ):
        while True:
            reply = self.c.wait_for_reply( "data" )

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
            self.c.relay_data( self.table_id, data, random_player(self) )


    def commit_deck( self ):
        commit = bit_commit( self.deck )
        commit = b64encode( commit.encode() ).decode("utf-8")
        my_commit = { str( self.player_num ): commit }
        self.passing_data[ "commits" ].update( my_commit )
        self.c.relay_data( self.table_id, self.passing_data, next_player(self) )

        while len( self.passing_data[ "commits" ] ) < 4:
            data = self.c.wait_for_reply( "data" )
            commits = data[ "commits" ]
            self.passing_data[ "commits" ].update( commits )
            self.c.relay_data( self.table_id, self.passing_data, next_player(self) )

        #TODO: Verify commits


    def share_deck_key( self ):
        my_key = { 
            str(self.player_num): {
                "pwd": b64encode( self.deck_pwd ).decode("utf-8"),
                "iv": b64encode( self.deck_iv ).decode("utf-8"),
            }
        }
        self.passing_data[ "deck_keys" ].update( my_key )
        self.c.relay_data( self.table_id, self.passing_data, next_player(self) )

        while len( self.passing_data[ "deck_keys" ] ) < 4:
            data = self.c.wait_for_reply( "data" )
            deck_keys = data[ "deck_keys" ]
            self.passing_data[ "deck_keys" ].update( deck_keys )
            self.c.relay_data( self.table_id, self.passing_data, next_player(self) )


    # Send passing_data to server to check if everyone has equal info
    def verify_equal_info( self ):
        pass


    def update_player_info( self ):
        for i in range(0, len(self.players)):
            # Retrieve from passing data
            commit = self.passing_data["commits"][str(i)]
            pwd = self.passing_data["deck_keys"][str(i)]["pwd"]
            iv = self.passing_data["deck_keys"][str(i)]["iv"]
            # Format
            commit = b64decode( commit.encode() )
            pwd = b64decode( pwd.encode() )
            iv = b64decode( iv.encode() )
            # Update
            self.players[i].bit_commit = commit
            self.players[i].deck_pwd = pwd
            self.players[i].deck_iv = iv


    def decrypt_deck( self ):
        for p in reversed(self.players):
            for i in range(0, len(self.deck)):
                self.deck[i] = security.AES_decrypt(
                    p.deck_pwd,
                    p.deck_iv,
                    self.deck[i]
                ).decode("utf-8")


    def start_game(self):
        print("\n\n\n\n\n")
        for d in self.passing_data:
            print( self.passing_data[d] )
        print("\n\nMy deck:", self.deck)
        
        print("The game is starting!")
        while True:
            time.sleep(1)

