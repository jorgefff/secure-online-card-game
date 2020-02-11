import socket 
import json
import select, os, sys
from sys import argv
import time, datetime
from base64 import b64decode, b64encode
from termcolor import colored
from cryptography import x509
from cryptography.hazmat.primitives import hashes  
from cryptography.hazmat.backends import default_backend
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import security
from hearts import Hearts

# Global vars
table_id_counter = 0
tables = {}
pre_registers = {}
clients = {}
buffer = []

# Address
IP = 'localhost'
SERVER_PORT = 50000
SV_ADDR = (IP, SERVER_PORT)

# Socket configs
BUFFER_SIZE = 64 * 1024

# TCP Socket
sock = socket.socket(
    socket.AF_INET, 
    socket.SOCK_STREAM
)
sock.setsockopt(
    socket.SOL_SOCKET,
    socket.SO_REUSEADDR, 
    1
)
sock.bind(SV_ADDR)

# Server diffie hellman
dh = security.Diffie_Hellman()
dh.generate_keys()

# End of message token
EOM = '---EOM---' 


def pre_register_client(client_socket):
    new_client = Client(client_socket)
    pre_registers[client_socket] = new_client


def send_pub_key(client_socket):
    c = pre_registers[ client_socket ]
    
    msg = {
        'pub_key': dh.share_key(),
        'iv': dh.share_iv(),
    }
    signature = dh.sign(json.dumps(msg))
    signature = b64encode(signature).decode('utf-8')

    msg = {
        'message': msg,
        'signature': signature,
    }

    msg = json.dumps(msg) + EOM 
    msg = msg.encode()
    client_socket.send(msg)


def register_client(msg, client_socket):
    c = pre_registers[ client_socket ]

    # Get all necessary fields
    signature = b64decode(msg['signature'])
    msg = msg['message']
    intent = msg['intent']
    name = msg['name']
    client_dh = security.DH_Params()
    client_dh.load_key(msg['pub_key'])
    client_dh.load_iv(msg['iv'])
    cert_msg = msg['certificate']

    # Validate certificate
    cl_cert = b64decode(msg['certificate'])
    chain = []
    for chain_cert in msg['chain']:
        chain.append(b64decode(chain_cert))
    
    if not security.validate_cert(cl_cert , chain):
        print(colored("Client '"+str(name)+"' certificate could not be verified", 'red'))
        del pre_registers[client_socket]
        return

    # Validate signature
    msg = json.dumps(msg)
    if not security.validate_cc_sign(msg, signature, cl_cert):
        print(colored("Client '"+str(name)+"' signature could not be verified", 'red'))
        del pre_registers[client_socket]
        return

    # Register
    c.name = name
    c.dh = client_dh
    c.chain = chain
    clients[client_socket] = c
    del pre_registers[client_socket]


def send_table_list(client_socket):
    table_list = []
    for table in tables.values():
        if table.state == 'OPEN':
            table_list.append({
                'id': table.table_id,
                'title': table.title,
                'player_count': table.player_count,
                'max_players': table.max_players})

    msg = {'table_list': table_list}

    client_socket.sign_and_send(msg)


def get_new_table_id():
    global table_id_counter
    new_id = table_id_counter
    table_id_counter += 1
    return new_id

    
def broadcast_new_player(players):
    player = players[-1]
    new_player = {
        'name': player.client.name,
        'num': player.num,
        'dh': {
            'pub_key': player.client.dh.share_key(),
            'iv': player.client.dh.share_iv(),
        },
    }

    for p in players[:-1]:
        msg = {
            'table_update': {
                'update': 'new_player', 
                'new_player': new_player}}
        p.client.sign_and_send(msg)



def broadcast_player_confirmation(players, pl_num):
    for p in players:
        msg = {
            'table_update': {
                'update': 'player_confirmation', 
                'player_num': pl_num}}
        p.client.sign_and_send(msg)


def broadcast_state_change(players, new_state):
    for p in players:
        msg = {
            'table_update': {
                'update': 'table_state', 
                'table_state': new_state}}
        p.client.sign_and_send(msg)


def generate_deck():
    deck = []
    suits = ["Sp", "Cl", "He", "Di"] # Spades Clubs Hearts Diamonds
    specials = ["A", "K", "Q", "J"]  # Ace King Queen Jack
    for suit in suits:
        for sp in specials:
            deck.append(suit + "-" + sp)
        for n in range(2,11):
            deck.append(suit + "-" + str(n))
    return [len(deck)] + deck


def join_table_handler (msg, client):
    table_id = msg['table_id']
    if table_id not in tables.keys():
        reply = {'error': 'Table not found'}
        client.send(reply)
        return

    table = tables[table_id]
    error = table.new_player(client)
    
    if error:
        reply = {'error': error}
        client.send(reply)
        return    
    
    reply = {
        'table_info': table.get_table_info(client)
    }
    client.sign_and_send(reply)
    
    broadcast_new_player(table.players)

    if table.is_full():
        table.state = 'FULL'
        broadcast_state_change(table.players, 'FULL')
        

def create_table_handler(msg, client):
    table_id = get_new_table_id()
    new_table = Table(table_id)
    new_table.new_player(client)
    
    tables[table_id] = new_table

    reply = {
        'table_info': new_table.get_table_info(client)
    }
    client.sign_and_send(reply)


def player_confirmation_handler(msg, client):
    sig = msg['signature']
    msg = msg['message']
    table_id = msg['table_id']
    identities = msg['identities']

    if table_id not in tables.keys():
        reply = {'error': 'Table not found'}
        client.sign_and_send(reply)
        return

    table = tables[table_id]
    error = table.confirm_player(client)
    
    if error:
        reply = {'error': error}
        client.sign_and_send(reply)
        return
    
    pl_num = table.get_player_num(client)
    broadcast_player_confirmation(table.players, pl_num)
    
    if table.all_confirmed():
        broadcast_state_change(table.players, 'SHUFFLE')
        deck = generate_deck()
        msg = {
            'from': 'croupier',
            'relayed': { 
                'deck': deck }
        }
        table.players[0].client.sign_and_send(msg)
    
def relay_handler(msg, client):
    msg = msg['message']
    table_id = msg['table_id']
    if table_id not in tables.keys():
        reply = {'error': 'Table not found'}
        client.sign_and_send(reply)
        return
    
    table = tables[table_id]
    if not table.player_exists(client):
        reply = {'error': 'You are not in this table'}
        client.sign_and_send(reply)
        return

    p_num = table.get_player(client).num

    relay_to = msg['relay_to']
    relay = {
        'from': p_num,
        'relayed': msg['relay'],
    }
    table.players[relay_to].client.sign_and_send(relay)
        

def bit_commit_handler(msg, client):
    table_id = msg['table_id']
    if table_id not in tables.keys():
        reply = {'error': 'Table not found'}
        client.sign_and_send(reply)
        return

    table = tables[table_id]
    commit = msg['bit_commit']
    error = table.add_commit(client, commit)

    if error:
        reply = {'error': error}
        client.sign_and_send(reply)
        return


def client_left_handler(client_sock):
    leavable_states = ['OPEN']
    client = clients[client_sock]
    for t in tables.values():
        if t.state in leavable_states:
            player = t.get_player(client)
            t.player_left(player.num)
            broadcast_player_left(t.players, player.num)
            del clients[client_sock]


def broadcast_player_left(players, player_num):
    for p in players:
        msg = {
            'table_update': {
                'update': 'player_left', 
                'player_left': player_num}}
        p.client.sign_and_send(msg)


def broadcast_game_abort(players, reason):
    pass


def pre_game_handler(msg, client):
    table_id = msg['table_id']
    if table_id not in tables.keys():
        reply = {'error': 'Table not found'}
        client.sign_and_send(reply)
        return

    table = tables[table_id]

    if client not in table.players:
        reply = {'error': 'Player not in this table'}
        client.sign_and_send(reply)
        return

    player = table.get_player(client)
    table.pre_game_infos[player.num] = msg['data']


    if len(table.pre_game_infos) == table.max_players:
        for i in range(table.max_players):
            for k in range(1, table.max_players):
                if table.pre_game_infos[0]['commits'][str(i)]['commit'] == table.pre_game_infos[k]['commits'][str(i)]['commit'] and \
                table.pre_game_infos[0]['commits'][str(i)]['r1'] == table.pre_game_infos[k]['commits'][str(i)]['r1'] and \
                table.pre_game_infos[0]['deck_keys'][str(i)]['pwd'] == table.pre_game_infos[k]['deck_keys'][str(i)]['pwd'] and \
                table.pre_game_infos[0]['deck_keys'][str(i)]['iv'] == table.pre_game_infos[k]['deck_keys'][str(i)]['iv']:
                    valid = True
                else:
                    valid = False
                    print("MISMATCH VALIDATIONS")
                    print(table.pre_game_infos)
                    break

        if valid:
            table.start_game()
            broadcast_state_change(table.players, 'game')
        else:
            broadcast_game_abort(table.players, 'MISMATCH VALIDATIONS')


def play_handler(full_msg, client):
    msg = full_msg['message']
    table_id = msg['table_id']
    if table_id not in tables.keys():
        reply = {'error': 'Table not found'}
        client.sign_and_send(reply)
        return

    table = tables[table_id]
    if table.state != 'game':
        reply = {'error': 'Game not started'}
        client.sign_and_send(reply)
        return

    game = table.game
    player = table.get_player(client).num
    card = msg['card']

    valid, error = game.valid_play(player, card)
    if not valid:
        reply = {'error': error}
        client.sign_and_send(reply)
        return

    game.new_play(player, card)
    broadcast_play(table.players, player, card, full_msg)

    if game.full_trick():
        print("FULL TRICK!")
        player_num, points = game.trick_outcome()
        broadcast_trick_outcome(table.players, player_num, points)

    if game.is_over():
        print("GAME OVER")
        winners, losers = game.game_outcome()
        broadcast_game_outcome(table.players, winners)
        


def broadcast_play(players, player, card, msg):
    proof = msg
    for p in players:
        msg = {
            'type': 'play',
            'from': player,
            'card': card, 
            'proof': proof,
        }
        p.client.sign_and_send(msg)


def broadcast_trick_outcome(players, player, points):
    for p in players:
        msg = {
            'type': 'trick_outcome',
            'player': player,
            'points': points,
        }
        p.client.sign_and_send(msg)


def broadcast_game_outcome(players, winners):
    for p in players:
        msg = {
            'type': 'game_outcome',
            'winners': winners
        }
        p.client.sign_and_send(msg)    


#########################################################################
## Client functions

class Client:
    def __init__ (self, socket):
        # Pre-register fields
        self.socket = socket
        self.dh = security.DH_Params()

        # Registered client fields
        self.name = None
        self.cert = None
        self.chain = None


    def send(self, msg):
        msg = json.dumps(msg) + EOM
        msg = msg.encode()
        try:
            self.socket.send(msg)
        except socket.error:
            print("This client is not connected!")


    def sign_and_send(self, msg):
        signature = dh.sign(json.dumps(msg))
        signature = b64encode(signature).decode('utf-8')
        msg = {
            'message': msg,
            'signature': signature,
        }
        self.send(msg)

    def __eq__(self, other):
        if isinstance(other, Player):
            return self == other.client
        return self.socket == other.socket


#########################################################################
## Player functions

class Player:
    def __init__ (self, client, num):
        self.points = 0
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
    def __init__ (self, table_id, title='Hearts'):
        self.table_id = table_id
        self.title = title
        self.max_players = 4
        self.state = 'OPEN'
        self.players = []
        self.player_count = 0
        self.players_confirmed = 0
        self.pre_game_infos = {}
        self.game = None

    def new_player (self, client):
        if client in self.players:
            return 'Already inside'
            
        if self.player_count >= self.max_players:
            return 'Table is full'
        
        self.players.append(Player(client, self.player_count))
        self.player_count += 1
    
        return None
    

    def player_exists (self, client):
        return client in self.players
        
    
    def is_full(self):
        return self.player_count == self.max_players


    def all_confirmed(self):
        return self.players_confirmed == self.max_players


    def player_left (self, num):
        del self.players[num]
        for p in self.players:
            p.confirmed = False
            if p.num > num:
                p.num -= 1
        self.players_confirmed = 0
        self.player_count -=1
        

    def get_table_info (self, client):
        return {
            'table_id': self.table_id,
            'title': self.title,
            'player_num': self.get_player_num(client),
            'players': self.get_players()
        }
        

    def get_player_num(self, client):
        return self.players.index(client)


    def get_player(self, client):
        i = self.players.index(client)
        return self.players[i]


    def get_players(self):
        p_list = []
        for p in self.players:
            p_list.append({
                'name': p.client.name,
                'num': p.num,
                'dh': {
                    'pub_key': p.client.dh.share_key(),
                    'iv': p.client.dh.share_iv(),
                },
            })
        return p_list
        

    def confirm_player (self, client):
        if client not in self.players:
            return 'Player is not in this table'
        
        if self.state != 'FULL':
            return 'Action not valid in current table state'

        player = self.get_player(client)
        if player.confirmed:
            return 'Player already confirmed'
        
        player.confirmed = True
        self.players_confirmed += 1
        return None
        

    def add_deck_key(self, client, key):
        if client not in self.players:
            return 'Player is not in this table'

        if self.state != 'SHUFFLING':
            return 'Action not valid in current table state'

        player = self.get_player(client)
        if player.deck_key:
            return 'Player already provided key'
        
        player.deck_key = key
        self.deck_keys += 1
        return None


    def add_commit(self, client, commit):
        if client not in self.players:
            return 'Player is not in this table'

        if self.state != 'SHUFFLING':
            return 'Action not valid in current table state'

        player = self.get_player(client)
        if player.deck_key:
            return 'Player already provided key'

        player.commit = commit
        self.commits += 1

    def start_game(self):
        self.state = 'game'
        self.game = Hearts()
        self.game.set_players(self.players)
        

#########################################################################
## Main server functions

def redirect_messages (full_msg, client_socket):
    try:
        msg = full_msg['message']
        intent = msg['intent']
    except:
        print("Invalid message format:\n", full_msg)
        return

    # New client
    if intent == 'register':
        register_client (full_msg, client_socket)

    # Registered client
    elif client_socket in clients.keys():
        client = clients[client_socket]

        # Doesnt require signature
        if intent == 'get_table_list':
            send_table_list (client)
            return

        try:
            signature = b64decode(full_msg['signature'])
        except:
            print("Invalid message format:\n", full_msg)
            return
        if not client.dh.valid_signature(
                json.dumps(msg), 
                signature):
            print("Invalid signature!")
            return

        # Following requests require signature
        if intent == 'join_table':
            join_table_handler (msg, client)
                    
        elif intent == 'create_table':
            create_table_handler (msg, client)
        
        elif intent == 'confirm_players':
            player_confirmation_handler(full_msg, client)

        elif intent == 'relay':
            relay_handler(full_msg, client)

        elif intent == 'validate_pre_game':
            pre_game_handler(msg, client)

        elif intent == 'bit_commit':
            bit_commit_handler(msg, client)

        elif intent == 'play':
            play_handler(full_msg, client)

        else:
            pass



print ("Starting table manager...")
sock.listen(1)
print ("Listening on port",SERVER_PORT,"\n")

read_list = [sock]

while True:
    
    if buffer:
        (s, msg) = buffer.pop(0)
        print("Processing:\n", data,"\n")
        msg = json.loads(msg)
        redirect_messages(msg , s)

    else:
        readable, writable, errored = select.select(read_list, [], [])
        for s in readable:
            
            #TODO
            #try: except ConnectionResetError as cre

            # New TCP connection
            if s is sock:
                client_socket, address = sock.accept()
                print("Connection from", address)
                read_list.append(client_socket)
                pre_register_client(client_socket)
                send_pub_key(client_socket)
            
            # Client sent a message
            else:
                received = s.recv (BUFFER_SIZE)
                if received:
                    data = received.decode().split(EOM)
                    for m in data[1:-1]:
                        if m:
                            buffer.append((s,m))
                    data = data[0]
                    
                    print("Received:\n", data,"\n")
                    msg = json.loads(data)
                    redirect_messages(msg, s)
                else:
                    if s in pre_registers:
                        print("Unregistered user has disconnected")
                        del pre_registers[s]
                    elif s in clients:
                        client_left_handler(s)
                    print("Client has disconnected")
                    s.close()
                    read_list.remove (s)
                    
                
