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
from hearts import Hearts
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import security

# Chances
PICK_CHANCE = 0.2
SWAP_CHANCE = 0.5
COMMIT_CHANCE = 0.5


def decide_to_pick():
    return rand.random() < PICK_CHANCE

def decide_to_swap():
    return rand.random() < SWAP_CHANCE

def decide_to_commit():
    return rand.random() < COMMIT_CHANCE


# Get next player
def next_player(table):
    idx = (table.myself + 1) % table.max_players
    player = table.players[idx]
    return player


# Returns a random player
def random_player(table, avoid=None):
    options = [0, 1, 2, 3]
    options.remove(table.myself)
    options.remove(avoid)
    rand_num = rand.choice(options)
    return table.players[ rand_num ]


# Shows the current state of the table
def print_lobby_state(table):
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
    def __init__(self, client, table_info, auto=False):#
        self.c = client
        self.auto = auto
        self.table_cmds = ['exit']
        self.table_id = table_info['table_id']
        self.title = table_info['title']
        self.myself = table_info['player_num']
        self.state = 'OPEN'
        
        self.players = [Player(p) for p in table_info['players']]
        self.pl_count = len(self.players)
        self.max_players = 4
        
        self.hand = []
        self.passing_data = {'commits': {}, 'deck_keys': {}}
        

    def start(self):
        self.wait_in_lobby()
        self.player_auth()
        self.player_confirmation()
        
        self.deck_encrypting()
        self.card_selection()
        self.commit_deck()
        self.share_deck_key()
        self.verify_equal_info()
        self.update_player_info()
        self.decrypt_hand()
        self.start_game()


    def update_state(self, new_state):
        self.state = new_state
        if new_state == "OPEN":
            self.table_cmds = ['exit']
        elif new_state == "FULL":
            self.table_cmds = ['exit", "confirm']
        else:
            self.table_cmds = []


    def new_player(self, player_info):
        new_player = Player(player_info)
        self.players.append(new_player)
        self.pl_count = len(self.players)
    

    def player_left(self, p_num):
        self.players.pop(p_num)
        self.pl_count = len(self.players)
        for p in self.players:
            p.confirmed = False
            if p.num > p_num:
                p.num -= 1
            

    def player_confirmed(self, player_num):
        self.players[ player_num ].confirmed = True


    def wait_in_lobby(self):
        # Wait for players to join the lobby
        auto_once = True
        while self.state in 'OPEN':

            print_lobby_state(self)
            msg, cmd = self.c.wait_for_reply_or_input(valid_cmds=self.table_cmds)
            
            # Received a message from server
            if msg:
                msg = msg['message']['table_update']
                update = msg['update']

                if update  == 'new_player':
                    self.new_player(msg['new_player'])

                elif update == 'player_left':
                    self.player_left(msg['player_left'])

                elif update == 'table_state':
                    self.update_state(msg['table_state'])
                
            # User input
            elif cmd:
                if cmd == 'exit':
                    exit()
    

    # Authenticate self and other players
    def player_auth(self):
        print(colored("Players authentication stage",'yellow'))
        print_lobby_state(self)

        # Self authentication
        my_auth = {
            'name': self.c.cc.name,
            'dh': {
                'pub_key': self.c.dh.share_key(),
                'iv': self.c.dh.share_iv(),
            },
            'certificate': self.c.cc.sendable_cert,
            'chain': self.c.cc.sendable_chain,
        }
        my_sig = self.c.cc.sign(json.dumps(my_auth))
        my_sig = b64encode(my_sig).decode('utf-8')

        my_msg = {
            'message': my_auth,
            'signature': my_sig,
        }
        
        # Relay auth to other players
        for p in self.players:
            if p.num != self.myself:
                self.c.relay_data(self.table_id, my_msg, p.num)
        
        self.players[self.myself].authd = True

        # Wait for other players to authenticate
        auths = 1
        buffer_reads = 0
        count_reads = False
        bypass = False
        while auths < self.max_players:
            if count_reads and buffer_reads >= len(self.c.buffer):
                bypass = True
                count_reads = False
                buffer_reads = 0

            msg = self.c.wait_for_reply(bypass_buffer=bypass)
            
            bypass = False
            if count_reads:
                buffer_reads += 1

            # Cycle buffer before checking for new msg
            if 'table_update' in msg['message'].keys():
                self.c.buffer.append(json.dumps(msg))
                count_reads = True
                continue
            
            src = msg['message']['from']
            
            relayed = msg['message']['relayed']
            signature = b64decode(relayed['signature'])
            relayed = relayed['message']

            # Build chain
            cert = b64decode(relayed['certificate'])
            chain = []
            for chain_cert in relayed['chain']:
                chain.append(b64decode(chain_cert))

            # Validate certification chain
            if not self.c.cc.validate_cert(cert , chain):
                print("Invalid certificate / chain from player:", src)
                exit()

            if not security.validate_cc_sign(json.dumps(relayed), signature, cert):
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
            {'name': p.name}
            for p in self.players
        ]
        confirmation = {
            'intent': 'confirm_players',
            'table_id': self.table_id,
            'identities': identities,
        }
        signature = self.c.dh.sign(json.dumps(confirmation))
        signature = b64encode(signature).decode('utf-8')
        my_confirmation = {
            'message': confirmation,
            'signature': signature,
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
            
            if count_reads and buffer_reads >= len(self.c.buffer):
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


    def deck_encrypting(self):
        print(colored("Encryping deck",'yellow'))
        reply = self.c.wait_for_reply()
        
        relayed = reply['message']['relayed']
        src = reply['message']['from']
        
        if type(reply['message']['relayed']) is not dict:
            src = self.players[int(src)]
            relayed = self.c.load_relayed_data(relayed, src.dh)

        deck = relayed['deck']

        # Generate deck password and IV
        self.deck_pwd = os.urandom(32)
        self.deck_iv = os.urandom(16)

        # Cipher each card        
        for i in range(1, len(deck)):
            deck[i] = security.AES_encrypt(
                pwd=self.deck_pwd,
                iv=self.deck_iv,
                text=deck[i]
           ).decode('utf-8')

        # Shuffle
        shuffled = deck[1:]
        rand.shuffle(shuffled)
        deck = deck[0:1] + shuffled
        data = { 'deck': deck }

        # Relay
        next_p = next_player(self)
        dst = next_p.num
        dh = next_p.dh
        self.c.relay_data(self.table_id, data, dst, dh, cipher=True)


    def card_selection(self):
        print(colored("Card selection",'yellow'))
        while True:
            reply = self.c.wait_for_reply()
            src = reply['message']['from']

            if type(reply['message']['relayed']) is not dict:
                src = self.players[int(src)]
                relayed = self.c.load_relayed_data(reply['message']['relayed'], src.dh)
            else:
                relayed = reply['message']['relayed']

            # Someone started bit commit process
            if 'commits' in relayed.keys():
                commits = relayed['commits']
                self.passing_data['commits'].update(commits)
                break
            
            deck_passing = relayed['deck'] 
            passing_size = deck_passing[0]
            deck_size = len(self.hand)

            # The passing deck is empty - decide if start commit process
            if passing_size == 0 and decide_to_commit():
                break
            
            # Pick one            
            elif deck_size < 13 and decide_to_pick():
                print("Taking a card")
                pick = rand.randrange(1, passing_size+1)
                card = deck_passing.pop(pick)
                deck_passing.append(security.rand_ciphered())
                self.hand.append(card)
                passing_size -= 1
                deck_size += 1
            
            # Swap cards
            if deck_size > 0 and passing_size > 0 and decide_to_swap():
                max_swaps = min(deck_size, passing_size)
                swaps = rand.randrange(1, max_swaps+1)
                while swaps > 0:
                    swaps -= 1
                    # Pick 2 random positions
                    passing_pick = rand.randrange(1, passing_size+1)
                    my_pick = rand.randrange(0, deck_size)
                    # Take the cards
                    passing_card = deck_passing[passing_pick]
                    my_card = self.hand[my_pick]
                    # Swap the cards
                    deck_passing[passing_pick] = my_card
                    self.hand[my_pick] = passing_card

            # Shuffle
            if passing_size > 1:
                shuffled = deck_passing[1:passing_size+1]
                rand.shuffle(shuffled)
                deck_passing[1:passing_size+1] = shuffled
            
            # Update size
            deck_passing[0] = passing_size

            # Send to random player
            data = {'deck': deck_passing }
            if src == 'croupier':
                avoid = None
            else:
                avoid = src.num
            dst = random_player(self, avoid)
            self.c.relay_data(self.table_id, data, dst.num, dst.dh, cipher=True)


    def commit_deck(self):
        data = sorted(self.hand)
        data = str(data)
        self.r1, self.r2, commit = security.bit_commit(data)

        commit = {
            str(self.myself): {
                'commit': b64encode(commit).decode('utf-8'),
                'r1': b64encode(self.r1).decode('utf-8'),
            } 
        }

        self.passing_data['commits'].update(commit)
        dst = next_player(self).num
        self.c.relay_data(self.table_id, self.passing_data, dst)

        while len(self.passing_data['commits']) < 4:
            msg = self.c.wait_for_reply()
            commits = msg['message']['relayed']['commits']
            self.passing_data['commits'].update(commits)
            dst = next_player(self).num
            self.c.relay_data(self.table_id, self.passing_data, dst)


    def share_deck_key(self):
        my_key = { 
            str(self.myself): {
                'pwd': b64encode(self.deck_pwd).decode('utf-8'),
                'iv': b64encode(self.deck_iv).decode('utf-8'),
            }
        }
        self.passing_data['deck_keys'].update(my_key)
        dst = next_player(self).num
        self.c.relay_data(self.table_id, self.passing_data, dst)

        while len(self.passing_data['deck_keys']) < 4:
            msg = self.c.wait_for_reply()
            deck_keys = msg['message']['relayed']['deck_keys']
            self.passing_data['deck_keys'].update(deck_keys)
            dst = next_player(self).num
            self.c.relay_data(self.table_id, self.passing_data, dst)


    # Send passing_data to server to check if everyone has equal info
    def verify_equal_info(self):
        self.c.validate_pre_game(self.table_id, self.passing_data)

        while True: 
            reply = self.c.wait_for_reply()
            if 'relayed' in reply['message'].keys():
                continue
            elif 'table_update' in reply['message'].keys():
                update_type = reply['message']['table_update']['update']
                if update_type == 'table_state':
                    new_state = reply['message']['table_update']['table_state']
                    if new_state == 'game':
                        print("Pre game data validated!")
                        break


    def update_player_info(self):
        for i in range(len(self.players)):
            # Retrieve from passing data
            commit = self.passing_data['commits'][str(i)]['commit']
            r1 = self.passing_data['commits'][str(i)]['r1']
            pwd = self.passing_data['deck_keys'][str(i)]['pwd']
            iv = self.passing_data['deck_keys'][str(i)]['iv']
            # Format
            commit = b64decode(commit.encode())
            r1 = b64decode(r1.encode())
            pwd = b64decode(pwd.encode())
            iv = b64decode(iv.encode())
            # Update
            self.players[i].bit_commit = commit
            self.players[i].r1 = r1
            self.players[i].deck_pwd = pwd
            self.players[i].deck_iv = iv


    def decrypt_hand(self):
        for p in reversed(self.players):
            for i in range(len(self.hand)):
                self.hand[i] = security.AES_decrypt(
                    p.deck_pwd,
                    p.deck_iv,
                    self.hand[i]
               ).decode('utf-8')


    def start_game(self):
        print("\n\n\n\n\n")
        # print("Commits:")
        # print(self.passing_data['commits'])
        # print("Deck keys:")
        # print(self.passing_data['deck_keys'])
        print("\n\nMy hand:", self.hand)
        print("The game is starting!")
        time.sleep(2)
        hearts = Hearts(self.table_id, self.c, self.players, self.myself, self.hand)
        hearts.set_auto(True)
        hearts.start()

