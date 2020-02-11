# Secure multiplayer Hearts game

## How to run the croupier

```
cd croupier
python3 server.py
```

## How to run the client

```
cd client/
python3 main.py <PORT> <JOIN/CREATE>
```
PORT is the port number used for the client
JOIN/CREATE to automically join or create a table upon connecting to the croupier


## TO-DO
* Automatize the process of getting the certificates
* Add cheating (there's already ways to detect it)
* Do something with when cheating is detected
