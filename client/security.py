import os
import random
import string
import hashlib
import binascii
import unicodedata
import base64

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
# https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/
def generate_priv_key():
    return rsa.generate_private_key( 
        public_exponent=65537, 
        key_size=1024, 
        backend=default_backend()
    )


# Generate RSA public key
# https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/
def generate_pub_key( privKey ):
    return privKey.public_key()


# https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/?highlight=rsa
def encrypt(pub_key, text):
    if type(text) is str:
        text = text.encode()
        text = base64.b64encode( text )
    ciphertext = pub_key.encrypt(
        text,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return ciphertext


# https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/?highlight=rsa
def decrypt( priv_key, ciphertext ):
    plaintext = priv_key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1( algorithm=hashes.SHA256() ),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    plaintext = base64.b64decode( plaintext )
    plaintext.decode('utf-8')
    return plaintext


# print( "Generate private key" )
# priv_k = generate_priv_key()

# print( "Generating public key" )
# pub_k = generate_pub_key( priv_k )

# plaintext = "blabla rawdawdawd 1023x"
# print( "\nPlaintext:\n", plaintext)

# #plaintext = base64.b64encode( plaintext.encode() )
# ciphered = encrypt( pub_k, plaintext )
# print( "\nCiphered text:\n", ciphered )

# deciphered = decrypt( priv_k, ciphered )
# print( "\nDeciphered text:\n", deciphered )

