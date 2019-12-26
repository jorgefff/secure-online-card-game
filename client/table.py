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
from cryptography import x509
from cryptography.hazmat.primitives import hashes  
from cryptography.hazmat.backends import default_backend
from termcolor import colored
from player import Player
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import security

# Chances
PICK_CHANCE = 0.5#0.05
SWAP_CHANCE = 0#0.5
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
def print_lobby_state( table ):
    print("\n\n\n\n\n------------------")    
    print("Current state:", table.state)

    if table.state == 'OPEN':
        print("Players:")
        for p in table.players:
            print(p.num+1, "-", p.name)
        print("\n")
        print("Commands: exit")

    elif table.state == 'FULL':
        print("Players:")
        for p in table.players:
            if p.confirmed:
                confirmed = colored("Yes",'green')
            else:
                confirmed = colored("No", 'red')
            if p.authd:
                authd = colored("Yes",'green')
            else:
                authd = colored("No",'red')
            print(p.num+1, "-", p.name,"- Auth:", authd, "- Confirmed:" ,confirmed)
        print("\n")
        print("Commands: confirm, exit")



#########################################################################
## Table class
class Table:
    def __init__( self, client, table_id, title, player_num, players, auto=False):
        self.auto = auto
        self.table_cmds = ['exit']
        self.table_id = table_id
        self.title = title
        self.player_num = player_num
        self.deck = []
        self.passing_data = {'commits': {}, 'deck_keys': {}}
        self.priv_deck_key = None
        self.pub_deck_key = None
        self.state = 'OPEN'
        self.players = players
        self.pl_count = len(self.players)
        self.max_players = 4
        self.c = client


    def start(self):
        self.wait_in_lobby()
        self.player_auth()
        self.player_confirmation()
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
            player["num"],
            player["name"],
            player["pub_key"]
        )
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
        while self.state in 'OPEN':

            print_lobby_state(self)
            msg, cmd = self.c.wait_for_reply_or_input( valid_cmds=self.table_cmds )
            
            # Received a message from server
            if msg:
                msg = msg['message']['table_update']
                update = msg['update']

                if update  == 'new_player':
                    self.new_player(msg['new_player'])

                elif update == 'player_left':
                    self.player_left(msg['player_num'])

                elif update == 'table_state':
                    self.update_state(msg['table_state'])
                
            # User input
            elif cmd:
                if cmd == 'exit':
                    #TODO: request to exit table and not close socket / client
                    exit()
    

    # Authenticate self and other players
    def player_auth( self ):
        print(colored("Players authentication stage",'yellow'))
        print_lobby_state(self)

        # Self authentication
        my_auth = {
            'name': self.c.cc.name,
            'pub_key': security.RSA_sendable_key( self.c.pub_key ),
            'certificate': self.c.cc.sendable_cert,
            'chain': self.c.cc.sendable_chain,
        }
        my_sig = self.c.cc.sign([
            my_auth['name'],
            my_auth['pub_key'],
            my_auth['certificate'],
            str(my_auth['chain']),
        ])
        my_msg = {
            'message': my_auth,
            'signature': b64encode(my_sig).decode('utf-8'),
        }
        
        # Relay auth to other players
        for p in self.players:
            if p.num != self.player_num:
                self.c.relay_data( self.table_id, my_msg, p)
        
        self.players[self.player_num].authd = True

        # Wait for other players to authenticate
        auths = 1
        buffer_reads = 0
        count_reads = False
        bypass = False
        while auths < self.max_players:
            if count_reads and buffer_reads >= len( self.c.buffer ):
                bypass = True
                count_reads = False
                buffer_reads = 0

            msg = self.c.wait_for_reply( bypass_buffer=bypass )
            
            bypass = False
            if count_reads:
                buffer_reads += 1

            # Cycle buffer before checking for new msg
            if 'table_update' in msg['message'].keys():
                self.c.buffer.append( json.dumps( msg ) )
                count_reads = True
                continue
            
            # sv_sig = reply['signature']
            src = msg['message']['from']
            
            relayed = msg['message']['relayed']#self.c.load_relayed_data( msg['message']['relayed'] )
            signature = b64decode( relayed['signature'] )
            relayed = relayed['message']
            # Build chain
            cert = b64decode( relayed['certificate'] )
            chain = []
            for chain_cert in relayed['chain']:
                chain.append( b64decode( chain_cert ) )

            # Validate certification chain
            if not self.c.cc.validate_cert( cert , chain):
                print("Invalid certificate / chain from player:",src)
                exit()

            fields = [
                relayed['name'],
                relayed['pub_key'],
                relayed['certificate'],
                str(relayed['chain']),
            ]

            if not security.validate_cc_sign( fields, signature, cert ):
                print("Invalid signature from player:", src)
                exit()


            # Update
            print("Player validated")
            self.players[src].certificate = cert
            self.players[src].sendable_cert = relayed['certificate']
            self.players[src].authd = True

            # Wait for next
            auths += 1
            print_lobby_state(self)


    # Confirm you want to play with these people
    def player_confirmation(self):
        print(colored("Confirmation stage",'yellow'))
        identities = [
            {   'num': p.num,
                'name': p.name,
                'pub_key': security.RSA_sendable_key( p.pub_key ),
            } 
            for p in self.players
        ]
        confirmation = {
            'intent': 'confirm_players',
            'table_id': self.table_id,
            'identities': identities,
        }
        fields = [
            confirmation['intent'],
            str(confirmation['table_id']),
            str(confirmation['identities']),
        ]
        signature = security.sign( fields, self.c.priv_key )
        my_confirmation = {
            'message': confirmation,
            'signature': b64encode(signature).decode('utf-8'),
        }
        
        confirms = 0
        confirmed = False
        buffer_reads = 0
        count_reads = False
        bypass = False
        while confirms < self.max_players or self.state=='FULL':
            # Automatic mode: send confirmation
            if self.auto and not confirmed and self.state == 'FULL':
                self.c.send(my_confirmation)
                confirmed = True
            
            if count_reads and buffer_reads >= len( self.c.buffer ):
                count_reads = False
                buffer_reads = 0
                bypass = True

            # Confirm or receive confirmations
            msg, cmd = self.c.wait_for_reply_or_input( 
                bypass_buffer=bypass,
                valid_cmds=self.table_cmds
            )

            bypass = False
            if count_reads:
                buffer_reads += 1
                
            
            # User input
            if cmd and cmd == 'confirm' and not confirmed:
                self.c.send(my_confirmation)
                confirmed = True
            
            # Received a message from server
            if msg:
                if 'relayed' in msg['message'].keys():
                    count_reads = True
                    continue

                msg = msg['message']['table_update']
                update = msg['update']

                if update  == 'player_confirmation':
                    self.player_confirmed(msg['player_num'])
                    confirms += 1

                elif update == 'player_left':
                    self.player_left(msg['player_num'])

                elif update == 'table_state':
                    self.update_state(msg['table_state'])

            # Wait for next
            print_lobby_state(self)


    def deck_encrypting( self ):
        print(colored("Encryping deck",'yellow'))
        reply = self.c.wait_for_reply()
        if type(reply['message']['relayed']) is str:
            relayed = self.c.load_relayed_data(reply['message']['relayed'])
        else:
            relayed = reply['message']['relayed']
        deck = relayed['deck']

        # Generate password and IV
        self.deck_pwd = os.urandom(32)
        self.deck_iv = os.urandom(16)
        # Cipher each card        
        for i in range(1, len(deck)):
            deck[i] = security.AES_encrypt(
                pwd=self.deck_pwd,
                iv=self.deck_iv,
                text=deck[i]
            ).decode('utf-8')
        # Shuffle and relay
        shuffled = deck[1:]
        rand.shuffle( shuffled )
        deck = deck[0:1] + shuffled
        data = { 'deck': deck }
        self.c.relay_data( self.table_id, data, next_player(self), cipher=True)


    def card_selection( self ):
        print(colored("Card selection",'yellow'))
        while True:
            reply = self.c.wait_for_reply()
            if type(reply['message']['relayed']) is str:
                relayed = self.c.load_relayed_data(reply['message']['relayed'])
            else:
                relayed = reply['message']['relayed']

            # Someone started bit commit process
            if 'commits' in relayed.keys():
                commits = relayed['commits']
                self.passing_data['commits'].update( commits )
                break
            
            deck_passing = relayed['deck'] 
            passing_size = deck_passing[0]
            deck_size = len( self.deck )

            # The passing deck is empty - decide if start commit process
            if passing_size == 0 and decide_to_commit():
                break
            
            # Pick one            
            elif deck_size < 13 and decide_to_pick():
                pick = rand.randrange( 1, passing_size+1 )
                card = deck_passing.pop( pick )
                deck_passing.append( security.rand_ciphered() )
                self.deck.append( card )
                passing_size -= 1
                deck_size += 1
            
            # Swap cards
            if deck_size > 0 and passing_size > 0 and decide_to_swap():
                max_swaps = min( deck_size, passing_size )
                swaps = rand.randrange( 1, max_swaps+1 )
                while swaps > 0:
                    swaps -= 1
                    # Pick 2 random positions
                    passing_pick = rand.randrange( 1, passing_size+1 )
                    my_pick = rand.randrange( 0, deck_size )
                    # Take the cards
                    passing_card = deck_passing[passing_pick]
                    my_card = self.deck[my_pick]
                    # Swap the cards
                    deck_passing[passing_pick] = my_card
                    self.deck[my_pick] = passing_card

            # Shuffle
            if passing_size > 1:
                shuffled = deck_passing[1:passing_size+1]
                rand.shuffle( shuffled )
                deck_passing[1:passing_size+1] = shuffled
            
            # Update size
            deck_passing[0] = passing_size

            # Send to random player
            data = {'deck': deck_passing }
            self.c.relay_data( self.table_id, data, random_player(self) )


    def commit_deck( self ):
        commit = 'BIT-COMMIT' #TODO
        commit = b64encode( commit.encode() ).decode('utf-8')
        my_commit = { str(self.player_num): commit }
        self.passing_data['commits'].update( my_commit )
        self.c.relay_data( self.table_id, self.passing_data, next_player(self) )

        while len( self.passing_data['commits'] ) < 4:
            msg = self.c.wait_for_reply()
            #relayed = self.c.load_relayed_data(data['message']['relayed'])
            commits = msg['message']['relayed']['commits']
            self.passing_data['commits'].update( commits )
            self.c.relay_data( self.table_id, self.passing_data, next_player(self) )


    def share_deck_key( self ):
        my_key = { 
            str(self.player_num): {
                'pwd': b64encode( self.deck_pwd ).decode('utf-8'),
                'iv': b64encode( self.deck_iv ).decode('utf-8'),
            }
        }
        self.passing_data['deck_keys'].update( my_key )
        self.c.relay_data( self.table_id, self.passing_data, next_player(self) )

        while len( self.passing_data['deck_keys'] ) < 4:
            msg = self.c.wait_for_reply()
            #relayed = self.c.load_relayed_data(data['message']['relayed'])
            deck_keys = msg['message']['relayed']['deck_keys']
            self.passing_data['deck_keys'].update( deck_keys )
            self.c.relay_data( self.table_id, self.passing_data, next_player(self) )


    # Send passing_data to server to check if everyone has equal info
    def verify_equal_info( self ):
        pass


    def update_player_info( self ):
        for i in range(0, len(self.players)):
            # Retrieve from passing data
            commit = self.passing_data['commits'][str(i)]
            pwd = self.passing_data['deck_keys'][str(i)]['pwd']
            iv = self.passing_data['deck_keys'][str(i)]['iv']
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
                ).decode('utf-8')


    def start_game(self):
        print("\n\n\n\n\n")
        for d in self.passing_data:
            print( self.passing_data[d] )
        print("\n\nMy deck:", self.deck)
        
        print("The game is starting!")
        exit()

