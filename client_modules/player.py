
class Player:
    def __init__( self, num, name, pub_key ):
        self.num = num
        self.name = name
        self.pub_key = pub_key
        self.deck_key = None
        self.score = 0
        self.rounds_won = 0
        self.confirmed = False

    def set_num( self, num ):
        self.num = num