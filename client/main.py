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
from client import Client
from table import Table
from player import Player
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import security


arg_sizes = [2, 3]
if len(argv) not in arg_sizes:
    print( "usages:" )
    print( "Manual usage: python3", argv[0], "<PORT NUMBER>" )
    print( "Automatic:    python3", argv[0], "<PORT NUMBER> <JOIN/CREATE>" )
    exit()

AUTO = False
CREATE = False
SERVER_PORT = 50000
IP = 'localhost'

CLIENT_PORT = int(argv[1])

if len(argv) == 3:
    AUTO = True
    CREATE = (argv[2].lower() == 'create')


# Clear ports
#os.system("kill -9 $(lsof -t -i:" + str(CLIENT_PORT) + ")")
#time.sleep(1)
#print("\n")
#sudo netstat -ap | grep 50000
#lsof -t -i:50000
#lsof -t -i:50001
#fuser -k 50001/tcp


#########################################################################
## Auxiliary functions

def print_client_options():
    print()
    print( "---------------------------------")
    print( "1 - Connect to server")
    print( "2 - List tables")
    print( "3 - Join table")
    print( "4 - Create table")
    print()
    print( "0 - Exit")
    print( "---------------------------------")
    print()


# Formats the table list from JSON to readable data
def format_table_list( table_list):
    # Formats the table list from JSON
    if not table_list:
        return ["No tables available"]

    new_list = []
    for t in table_list:
        id              = str(t['id'])
        title           = str(t['title'])
        player_count    = str(t['player_count'])
        max_players     = str(t['max_players'])
        line = id+" - "+title+" - ["+player_count+"/"+max_players+"]"
        new_list.append(line)

    return new_list


def main():
    print( "Starting client" )
    c = Client(IP, CLIENT_PORT)
    while True:
        print_client_options()
        opt = input("> ")
        if not (opt.isdigit() and int(opt) >= 0 and int(opt) < 5):
            continue
        
        opt = int(opt)
        reply = None

        # Close
        if opt == 0:
            c.close()
            exit()
        
        # Join server
        elif opt == 1:
            c.join_server( IP, SERVER_PORT )

        # Get table list
        elif opt == 2:
            table_list = c.get_tables()
            fmtd_table_list = format_table_list( table_list)
            print( "Tables:")
            for table in fmtd_table_list:
                print( "   "+table)

        # Join a table
        elif opt == 3:
            while True:
                try:
                    table_id = int(input("Table number: "))
                    break
                except:
                    print("Not a number!")
            reply = c.join_table( table_id )

        # Create new table
        elif opt == 4:
            reply = c.create_table()

        if reply:
            table = Table(
                client=c,
                table_info=reply,
            )       
            table.start()


def automatic_main():
    print("Starting automatic client")
    c = Client(IP, CLIENT_PORT)
    print("Connecting...")
    
    while not c.join_server(IP, SERVER_PORT):
        time.sleep(1)
    
    reply = None
    while not reply:
        # Going to create a new table
        if CREATE:
            print("\nCreating table")
            reply = c.create_table()
            time.sleep(1)
        # Going to join an existing table
        else:
            time.sleep(1)
            tables = c.get_tables()
            if len(tables) > 0:
                table_id = tables[0]['id']
                print("Joining table")
                time.sleep(1)
                reply = c.join_table(table_id)

    table = Table(
        client=c,
        table_info=reply,
        auto=True,
    )     
    table.start()


if __name__ == "__main__":
    if AUTO:
        automatic_main()
    else:
        main()
