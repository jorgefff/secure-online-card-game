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
def RSA_generate_priv():
    return rsa.generate_private_key( 
        public_exponent=65537, 
        key_size=1024, 
        backend=default_backend()
    )


# Generate RSA public key from a private key
def RSA_generate_pub( privKey ):
    return privKey.public_key()


def RSA_encrypt( key, text ):
    if type(text) is str:
        text = text.encode()
    
    chunk_size = ( key.key_size // 8) - 2 * hashes.SHA256.digest_size - 2

    ciphertext = b''
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end > len(text):
            end = len(text)
        block = key.encrypt(
            text[start:end],
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        start = end
        ciphertext += block
        
    return b64encode( ciphertext )


def RSA_decrypt( priv_key, ciphertext ):
    chunk_size = 128
    ciphertext = b64decode( ciphertext )
    plaintext = b''
    start = 0
    while start < len(ciphertext):
        end = start + chunk_size
        
        if end > len(ciphertext):
            end = len(ciphertext)
        
        block = priv_key.decrypt(
            ciphertext[start:end],
            padding.OAEP(
                mgf=padding.MGF1( algorithm=hashes.SHA256() ),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        start = end
        plaintext += block

    return plaintext.decode('utf-8')


# Gets the bytes from this public key
def RSA_key_bytes( key ):
    key_bytes = key.public_bytes(
        encoding = serialization.Encoding.PEM,
        format = serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return key_bytes.decode('utf-8')


# Loads a public key from the bytes of another public key
def RSA_load_key( key_bytes ):
    if type(key_bytes) is str:
        key_bytes = key_bytes.encode()
    return serialization.load_pem_public_key(
        key_bytes,
        backend=default_backend()
    )
    

def AES_encrypt(pwd, iv, text):
    if type(text) is str:
        text = text.encode()
    
    cipher = Cipher(
        algorithm=algorithms.AES(pwd),
        mode=modes.CTR(iv),
        backend=default_backend()
    )
    encryptor = cipher.encryptor()
    
    return b64encode(
        encryptor.update(text) + encryptor.finalize()
    )
    


def AES_decrypt(pwd, iv, ciphered):
    ciphered = b64decode( ciphered )
    decipher = Cipher(
        algorithm=algorithms.AES(pwd),
        mode=modes.CTR(iv),
        backend=default_backend()
    )
    decryptor = decipher.decryptor()
    return decryptor.update(ciphered) + decryptor.finalize()


############### DEBUG

# print( "Generate private key" )
# priv_k = generate_priv_key()

# print( "Generating public key" )
# pub_k = generate_pub_key( priv_k )

# import json

# msg = { "pubkey": get_key_bytes( pub_k ) }
# msg = json.dumps( msg )

# rcv = json.loads(msg)
# key = load_key_from_bytes( rcv["pubkey"] )


# text = "-----BEGIN PUBLIC KEY-----\nMIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC+UwN4n8Jx8Ju4uXQwQBTqfnZS\nYZLzw8g53NkalghcWcBwy+tdkKiK6PlVfuqc+DuFShWOKdasgZk82d2oMf7mHxLM\nZii/MXNgmOtnlw+gFrdWSbatn4P3eRt7I6g8uR5scoCXek3mU4zskb7ZAdLQw1Jo\naUIn0sAIDfJS3g0aMQIDAQAB\n-----END PUBLIC KEY-----\n"

# en = encrypt(pub_k, text)
# de = decrypt(priv_k, en)

pwd = os.urandom(32)
iv = os.urandom(16)

t = "aaaabbbbbbbc"

ciph = AES_encrypt(pwd,iv,t)
print("Ciph:",ciph)
plain = AES_decrypt(pwd,iv, ciph)
print("Decip:",plain)