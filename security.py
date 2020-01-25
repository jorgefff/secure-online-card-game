import os
import random
import string
import hashlib
import binascii
import unicodedata
from base64 import b64decode, b64encode
from cryptography.exceptions import *
from math import *
from datetime import datetime
from OpenSSL import crypto

from Crypto.Cipher import AES
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec
from cryptography.hazmat.primitives import padding as prim_padding
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

chosen_hash = hashes.SHA1()

# Generate a RSA private key
def RSA_generate_priv():
    return rsa.generate_private_key(
        public_exponent=65537, 
        key_size=1024, 
        backend=default_backend()
   )


# Generate RSA public key from a private key
def RSA_generate_pub(priv_key):
    return priv_key.public_key()


# Encrypts with with a public key
def RSA_encrypt(pub_key, text):
    if type(text) is str:
        text = text.encode()
    
    chunk_size = (pub_key.key_size // 8) - 2 * hashes.SHA256.digest_size - 2
    ciphertext = b''
    start = 0

    while start < len(text):
        end = start + chunk_size
        if end > len(text):
            end = len(text)
        block = pub_key.encrypt(
            text[start:end],
            padding.OAEP(
                mgf=padding.MGF1(algorithm=chosen_hash),
                algorithm=chosen_hash,
                label=None
           )
       )
        start = end
        ciphertext += block

    return b64encode(ciphertext)


def to_b64_txt(value):
    if type(value) is str:
        value = value.encode()
    return b64encode(value).decode('utf-8')


def load_b64(value):
    return b64decode(value)


# Decrypts with private key
def RSA_decrypt(priv_key, ciphertext):
    chunk_size = 128
    ciphertext = b64decode(ciphertext)
    plaintext = b''
    start = 0
    
    while start < len(ciphertext):
        end = start + chunk_size
        
        if end > len(ciphertext):
            end = len(ciphertext)
        
        block = priv_key.decrypt(
            ciphertext[start:end],
            padding.OAEP(
                mgf=padding.MGF1(algorithm=chosen_hash),
                algorithm=chosen_hash,
                label=None
           )
       )
        start = end
        plaintext += block

    return plaintext.decode('utf-8')


# Gets the bytes from this public key
def RSA_sendable_key(key):
    key_bytes = key.public_bytes(
        encoding = serialization.Encoding.PEM,
        format = serialization.PublicFormat.SubjectPublicKeyInfo
   )
    return key_bytes.decode('utf-8')


# Loads a public key from the bytes of another public key
def RSA_load_key(key_bytes):
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
    ciphered = b64decode(ciphered)
    decipher = Cipher(
        algorithm=algorithms.AES(pwd),
        mode=modes.CTR(iv),
        backend=default_backend()
   )
    decryptor = decipher.decryptor()
    return decryptor.update(ciphered) + decryptor.finalize()


def rand_ciphered(p_siz=32, i_siz=16, s_siz=12):
    pwd = os.urandom(p_siz)
    iv = os.urandom(i_siz)
    randstring = os.urandom(s_siz)
    return b64encode(AES_encrypt(pwd, iv, randstring)).decode('utf-8')


def validate_cert(cert, chain):
    # Transform bytes into certificate
    cert = x509.load_der_x509_certificate(cert, default_backend())
    cert_name = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value+".cer"

    # Get list of trusted certificates by the server        
    trusted_certs = [
        f 
        for f in os.listdir("server_trusted_certs") 
        if os.path.isfile(os.path.join("server_trusted_certs", f))
    ]
    
    # Get list of trusted certificates by server from the clients 
    trusted_client_certs = [
        f 
        for f in os.listdir("server_trusted_certs/client_certs") 
        if os.path.isfile(os.path.join("server_trusted_certs/client_certs", f))
    ]

    if cert_name in trusted_certs:
        with open(os.path.join("server_trusted_certs", cert_name),"rb") as f:

            if cert == x509.load_der_x509_certificate(f.read(), default_backend()):
                crl_name = "CRL/cc_ec_cidadao_crl00"+cert_name[-5]+"_crl.crl"
                with open(crl_name, "rb") as ff:
                    crl = x509.load_der_x509_crl(ff.read(), default_backend())

                if crl.get_revoked_certificate_by_serial_number(cert.serial_number) == None:
                    print(" > CERTIFICATE \'{}\' IS TRUSTED".format(cert_name))
                    return True
                else:
                    print("Certificate {} has expired".format(cert_name))
                    return False
                
    elif cert_name in trusted_client_certs:
        with open(os.path.join("server_trusted_certs/client_certs", cert_name),"rb") as f: 
            if cert == x509.load_der_x509_certificate(f .read(), default_backend()):
                print(" > CERTIFICATE \'{}\' IS TRUSTED".format(cert_name))
                return True

    else:
        pass #print(" > CERTIFICATE \'{}\' NOT PART OF TRUSTED CERTIFICATES".format(cert_name))
            
    # Verify the chain
    if len(chain) != 0:
        try:
            return validate_cert(chain[0],chain[1:])
        except ValueError:
            raise ValueError
        except Exception as e:
            raise e
    else:
        raise ValueError

    # Add new certificate to server_trusted_certs folder
    with open("server_trusted_certs/client_certs/"+cert_name, "wb") as f:
        f.write(cert.public_bytes(Encoding.DER))


# Signs a message with private key
def sign(msg_fields, priv_key):
    hashing = hashes.Hash(choosen_hash, default_backend())
    for field in msg_fields:
        hashing.update(field.encode())
    digest = hashing.finalize()

    return priv_key.sign(
			digest,
			padding.PSS(mgf=padding.MGF1(chosen_hash),salt_length=padding.PSS.MAX_LENGTH),
			chosen_hash)


# Validates a signature made with a RSA private key
def validate_rsa_sign(msg_fields, signature, pub_key):
    # Rebuild signature
    hasher = hashes.Hash(chosen_hash, default_backend())
    for field in msg_fields:
        hasher.update(field.encode())    
    digest = hasher.finalize()

    return pub_key.verify(
			signature,
			digest,
			padding.PSS(mgf=padding.MGF1(chosen_hash),salt_length=padding.PSS.MAX_LENGTH),
			chosen_hash)


# Validates a signature made with a citizen card
def validate_cc_sign(msg, sig, certificate):
    # Get key from certificate
    cert_der = x509.load_der_x509_certificate(certificate, default_backend())
    cc_key = cert_der.public_key()

    # Rebuild signature
    hasher = hashes.Hash(chosen_hash, default_backend())
    # for field in msg_fields:
    #     hasher.update(field.encode())    
    hasher.update(msg.encode())
    digest = hasher.finalize()

    # Verify
    try:
        cc_key.verify(sig, digest, padding.PKCS1v15(), chosen_hash)
    except:
        return False
    return True


class Diffie_Hellman:
    def __init__(self):
        self.private_key = None
        self.public_key = None
        self.iv = None

    def generate_keys(self):
        self.private_key = ec.generate_private_key(ec.SECP384R1(), default_backend())
        self.public_key = self.private_key.public_key()
        self.iv = os.urandom(16)
        

    def share_key(self):
        return self.public_key.public_bytes(
            encoding = serialization.Encoding.PEM,
            format = serialization.PublicFormat.SubjectPublicKeyInfo
       ).decode('utf-8')


    def share_iv(self):
        return b64encode(self.iv).decode('utf-8')


    def sign(self, msg):
        hashing = hashes.Hash(chosen_hash, default_backend())
        hashing.update(msg.encode())
        digest = hashing.finalize()

        signature = self.private_key.sign(
            digest,
            ec.ECDSA(chosen_hash)
        )
        return signature


    def encrypt(self, plaintext, shared_key, iv=None):
        if iv is None:
            iv = self.iv
        if type(plaintext) is str:
            plaintext = plaintext.encode()

        shared_key = self.private_key.exchange(ec.ECDH(), shared_key)
        derived_key = HKDF(
            algorithm=chosen_hash,
            length=32,
            salt=None,
            info=None,
            backend=default_backend()
       ).derive(shared_key)

        aes = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        encryptor = aes.encryptor()

        padder = prim_padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext) + padder.finalize()
        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        return b64encode(encrypted)


    def decrypt(self, ciphertext, shared_key, iv=None):
        if iv is None:
            iv = self.iv
        if type(ciphertext) is str:
            ciphertext = ciphertext.encode()
        ciphertext = b64decode(ciphertext)

        shared_key = self.private_key.exchange(ec.ECDH(), shared_key)
        derived_key = HKDF(
            algorithm=chosen_hash,
            length=32,
            salt=None,
            info=None,
            backend=default_backend()
       ).derive(shared_key)

        aes = Cipher(algorithms.AES(derived_key), modes.CBC(iv), backend=default_backend())
        decryptor = aes.decryptor()
        decrypted_data = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = prim_padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(decrypted_data) + unpadder.finalize()
        return decrypted.decode('utf-8')


class DH_Params:
    def __init__(self, dh_json=None):
        if dh_json is not None:
            self.load_key(dh_json['pub_key'])
            self.load_iv(dh_json['iv'])
        else:
            self.public_key = None
            self.iv = None

    def load_key(self, public_key):
        if type(public_key) is str:
            public_key = public_key.encode()
        self.public_key = serialization.load_pem_public_key(
            public_key,
            backend=default_backend()
       )

    def load_iv(self, iv):
        if type(iv) is str:
            iv = iv.encode()
        iv = b64decode(iv)
        self.iv = iv

    def share_key(self):
        return self.public_key.public_bytes(
            encoding = serialization.Encoding.PEM,
            format = serialization.PublicFormat.SubjectPublicKeyInfo
       ).decode('utf-8')


    def share_iv(self):
        return b64encode(self.iv).decode('utf-8')

    def valid_signature(self, msg, signature):
        hashing = hashes.Hash(choosen_hash, default_backend())
        hashing.update(msg.encode())
        digest = hashing.finalize()

        try:
            self.public_key.verify(signature, msg, ec.ECDSA(choosen_hash))
        except:
            return False

        return True
