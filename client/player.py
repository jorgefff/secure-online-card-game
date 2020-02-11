import sys, os
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import security

class Player:
    def __init__(self, player_info):
        self.num = player_info['num']
        self.name = player_info['name']
        self.dh = security.DH_Params(player_info['dh'])
        
        self.certificate = None
        self.sendable_cert = None
        self.authd = False
        self.confirmed = False

        self.deck_key = None
        self.deck_iv = None
        
        self.bit_commit = None
        self.r1 = None
        self.r2 = None

        self.played_cards = []
        self.suits = ['Cl','He','Di','Sp']
        self.points = 0
        

    def set_num(self, num):
        self.num = num