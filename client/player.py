import sys, os
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import security

class Player:
    def __init__(self, player_info):
        self.num = player_info['num']
        self.name = player_info['name']
        self.dh = security.DH_Params(player_info['dh'])
        self.deck_key = None
        self.deck_iv = None
        self.bit_commit = None
        self.score = 0
        self.rounds_won = 0
        self.certificate = None
        self.sendable_cert = None
        self.authd = False
        self.confirmed = False

    def set_num(self, num):
        self.num = num