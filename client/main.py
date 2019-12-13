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
from table import Table
from player import Player
from client import Client

# Select port
AUTO = False
AUTO_PORTS = [52001,52002,52003,52004]

if len(argv) < 2:
    print( "usages:")
    print("python3 player_client.py <PORT_NUMBER>")
    print("python3 player_client.py AUTO <1-4>")
    exit()
if argv[1].lower() == "auto":
    if not argv[2].isdigit:
        print("python3 player_client.py AUTO <1-4>")
        exit()
    AUTO = True
elif not argv[1].isdigit:
    print( "Port argument needs to be an integer")
    exit()
elif int(argv[1]) < 1:
    print( "port number needs to be > 0")
    exit()


# Address constants
IP = "localhost"
if AUTO:
    PORT = AUTO_PORTS[int(argv[2])]
else:
    PORT = int(argv[1])
SERVER_PORT = 50000
CLIENT_PORT = PORT


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
        id              = str(t.get("id"))
        title           = str(t.get("title"))
        player_count    = str(t.get("player_count"))
        max_players     = str(t.get("max_players"))
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
            reply = c.create_table

        if reply:
            table = Table(
                c,
                reply.get("table_id"),
                reply.get("title"),
                reply.get("player_num"),
                [ Player(
                    p.get("num"),
                    p.get("name"),
                    p.get("pub_key")) 
                    for p in reply.get( "players" )
                ]
            )       
            table.start()


def automatic_main():
    print("Starting automatic client")
    c = Client(IP, CLIENT_PORT)
    print("Connecting...")
    c.join_server(IP, SERVER_PORT)
    time.sleep(1)
    
    if PORT == AUTO_PORTS[0]:
        print("\nCreating table")
        reply = c.create_table()
    else:
        time.sleep(1)
        c.list_tables()
        print("Joining table")
        time.sleep(3)
        reply = c.join_table(0)

    table = Table(
        c,
        reply.get("table_id"),
        reply.get("title"),
        reply.get("player_num"),
        [ Player(
            p.get("num"),
            p.get("name"),
            p.get("pub_key")) 
            for p in reply.get( "players" )
        ],
        auto=True
    )     
    table.start()


if __name__ == "__main__":
    if AUTO:
        automatic_main()
    else:
        main()
