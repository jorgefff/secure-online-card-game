import os
import random
import string
import hashlib
import binascii
import unicodedata
from base64 import b64decode, b64encode

from math import *
from datetime import datetime
from OpenSSL import crypto

from Crypto.Cipher import AES
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


# Generate a RSA private key
def generate_priv_key():
    return rsa.generate_private_key( 
        public_exponent=65537, 
        key_size=1024, 
        backend=default_backend()
    )


# Generate RSA public key from a private key
def generate_pub_key( privKey ):
    return privKey.public_key()


def encrypt( key, text ):
    if type(text) is str:
        text = text.encode()
        text = b64encode( text )
    ciphertext = key.encrypt(
        text,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return ciphertext


def decrypt( priv_key, ciphertext ):
    plaintext = priv_key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1( algorithm=hashes.SHA256() ),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    plaintext = b64decode( plaintext )
    plaintext.decode('utf-8')
    return plaintext


# Gets the bytes from this public key
def get_key_bytes( key ):
    key_bytes = key.public_bytes(
        encoding = serialization.Encoding.PEM,
        format = serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return key_bytes.decode('utf-8')


# Loads a public key from the bytes of another public key
def load_key_from_bytes( key_bytes ):
    if type(key_bytes) is str:
        key_bytes = key_bytes.encode()
    return serialization.load_pem_public_key(
        key_bytes,
        backend=default_backend()
    )
    



############### DEBUG

# print( "Generate private key" )
# priv_k = generate_priv_key()

# print( "Generating public key" )
# pub_k = generate_pub_key( priv_k )

# # plaintext = "blabla rawdawdawd 1023x"
# # print( "\nPlaintext:\n", plaintext)

# # ciphered = encrypt( pub_k, plaintext )
# # print( "\nCiphered text:\n", ciphered )

# # deciphered = decrypt( priv_k, ciphered )
# # print( "\nDeciphered text:\n", deciphered )

# import json

# msg = { "pubkey": get_key_bytes( pub_k ) }
# msg = json.dumps( msg )

# rcv = json.loads(msg)
# key = load_key_from_bytes( rcv["pubkey"] )


# t = "abc123123"

# cipher = encrypt(key, t)

# decipher = decrypt(priv_k, cipher)

# print("Text:\n",t)

# print("Ciphered:\n",cipher)

# print("Deciphered:\n",decipher)

