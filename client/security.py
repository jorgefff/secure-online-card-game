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


# function to generate a 1024 bits RSA private key
# https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/
def generate_priv_key():
    return rsa.generate_private_key( 65537, 1024, backend=default_backend() )


# function to generate a (same amount of bits) RSA public key
# https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/
def generate_pub_key( privKey ):
    return privKey.public_key()


# https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/?highlight=rsa
def encrypt(pub_key, message):
		ciphertext = pub_key.encrypt(
			message,
			padding.OAEP(
				mgf=padding.MGF1(algorithm=hashes.SHA256()),
				algorithm=hashes.SHA256(),
				label=None
			)
		)
		return ciphertext


# https://cryptography.io/en/latest/hazmat/primitives/asymmetric/rsa/?highlight=rsa
def decrypt( priv_key, ciphertext ):
    plainText = priv_key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1( algorithm=hashes.SHA256() ),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return plainText


print( "Generate private key" )
priv_k = generate_priv_key()

print( "Generating public key" )
pub_k = generate_pub_key( priv_k )

plaintext = "blabla rawdawdawd 1023x"
print( "\nPlaintext:\n", plaintext)

plaintext = base64.b64encode( plaintext.encode() )
ciphered = encrypt( pub_k, plaintext )
print( "\nCiphered text:\n", ciphered )

deciphered = base64.b64decode( decrypt( priv_k, ciphered ) ).decode('utf-8')
print( "\nDeciphered text:\n", deciphered )

