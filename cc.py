
import os
import platform
from PyKCS11 import *

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_der_public_key, Encoding, PublicFormat
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils
from cryptography import x509
from cryptography.x509.oid import NameOID
from termcolor import colored
from base64 import b64decode, b64encode

PKCS11_LIB_LINUX = "/usr/local/lib/libpteidpkcs11.so"
PKCS11_LIB_WINDOWS = "c:\\Windows\\System32\\pteidpkcs11.dll"

class CitizenCard:
    def __init__(self):
        self.PKCS11_LIB = None
        self.pkcs11 = None
        self.slot = None
        self.PKCS11_session = None
        self.name = None
        print("============================")
        if  self._check_lib_files() and \
            self._load_lib_files():
            self.get_session()
            self.extract_certificates()
        print("============================\n")
        self.certificate = self.get_certificate('AUTHENTICATION')
        self.sendable_cert = b64encode(self.certificate).decode('utf-8')
        cert = x509.load_der_x509_certificate(self.certificate, default_backend())
        subject = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        self.subject = subject
        self.name = subject
        self.pub_cc_key = cert.public_key()
        self.chain = []
        self.sendable_chain = []
        for chain_cert in self.get_chain(subject):
            self.chain.append(chain_cert)
            self.sendable_chain.append(b64encode(chain_cert).decode('utf-8'))

    def _check_lib_files(self):
        print("Checking PKCS11 necessary files")
        if platform.uname().system == "Linux":
            print("Linux system detected")
            print("Checking for:", PKCS11_LIB_LINUX)
            if os.path.isfile(PKCS11_LIB_LINUX):
                print("PKCS11 lib found")
                self.PKCS11_LIB = PKCS11_LIB_LINUX
                return True
            else:
                print(colored("PKCS11 lib not found",'red'))

        elif platform.uname().system == "Windows":
            print("Windows system detected")
            print("Checking for:", PKCS11_LIB_WINDOWS)
            if os.path.isfile(PKCS11_LIB_WINDOWS):
                print("PKCS11 lib found")
                self.PKCS11_LIB = PKCS11_LIB_WINDOWS
                return True
            else:
                print(colored("PKCS11 lib not found",'red'))
        else:
            print(colored("Unsupported system",'red'))

    def _load_lib_files(self):
        self.pkcs11 = PyKCS11.PyKCS11Lib()
        try:
            self.pkcs11.load(self.PKCS11_LIB)
            print("Lib loaded successfully")
            slots = self.pkcs11.getSlotList()
            if not slots:
                print(colored("Card reader not found",'red'))
                return False
            print("Card reader found")
            self.slot = slots[0]
            return True
        except PyKCS11.PyKCS11Error:
            print(colored("Could not load lib and get slot list",'red'))
            return False
        

    # Returns CC session, if there isnt one creates new
    def get_session(self):
        if self.slot is None:
            print(colored("Card reader not found",'red'))
            return None
        if self.PKCS11_session:
            return self.PKCS11_session
        print("Creating new PKCS11 session")
        self.PKCS11_session = self.pkcs11.openSession( self.slot )
        return self.PKCS11_session
        

    # Extract the certificates from the Citizen Card
    def extract_certificates(self):
        session = self.PKCS11_session
        print("Starting certificate extraction")
        # Name of the directory where the certificates will be stored
        path = "client_certificates"
        # Create the directory
        if not os.path.exists(path):
            print("\tCreating directory to store certificates\n")
            os.mkdir(path)

        # Name of the directory where the certificate is stored
        path = os.path.join(path)
        # Create the directory
        if not os.path.exists(path):
            print("\tCreating directory to store user's certificates\n")
            os.mkdir(path)

        if session is not None:
            # Find all the certificates
            try:
                objects = session.findObjects([(PyKCS11.CKA_CLASS, PyKCS11.CKO_CERTIFICATE)])
            except PyKCS11.PyKCS11Error:
                print(colored("\tCard not found",'red'))
                return False
            
            for obj in objects:
                # Obtain attributes from certificate
                try:
                    attributes = session.getAttributeValue(obj, [PyKCS11.CKA_VALUE])[0]
                except PyKCS11.PyKCS11Error as e:
                    continue

                # Load certificate from DER format
                cert = x509.load_der_x509_certificate(bytes(attributes), default_backend())
                # Obtain certificate's subject
                subject = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
                # Obtain certificate's issuer
                issuer = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
                
                # if self.name is None:
                #     self.name = subject

                print("\t-------------")
                print("\tSubject:",subject)
                print("\tIssuer:",issuer)
                
                try:
                    # 
                    if "EC de Autenticação do Cartão de Cidadão" in subject or \
                            "EC de Autenticação do Cartão de Cidadão" in issuer:
                        # Create the directory
                        if not os.path.exists(os.path.join(path,"ECs de Autenticação")):
                            os.mkdir(os.path.join(path,"ECs de Autenticação"))
                        # Save certificate in directory
                        with open(path+"/ECs de Autenticação/"+str(subject)+".cer", "wb") as f:
                            f.write(cert.public_bytes(Encoding.DER))

                    elif "EC de Assinatura Digital Qualificada do Cartão de Cidadão" in subject or \
                            "EC de Assinatura Digital Qualificada do Cartão de Cidadão" in issuer:
                        # Create the directory
                        if not os.path.exists(os.path.join(path,"ECs de Assinatura Digital")):
                            os.mkdir(os.path.join(path,"ECs de Assinatura Digital"))
                        # Save certificate in directory
                        with open(path+"/ECs de Assinatura Digital/"+str(subject)+".cer","wb") as f:
                            f.write(cert.public_bytes(Encoding.DER))

                    else:
                        # Save certificate in directory
                        if not os.path.isfile(path+"/"+str(subject)+".cer"):
                            with open(path+"/"+str(subject)+".cer", "wb") as f:
                                f.write(cert.public_bytes(Encoding.DER))
                except Exception as e:
                    print(colored("\tException:",'red'))
                    print("\t",e)
        print()
        return True


    # Get the chain of a given certificate
    def get_chain(self, cert):
        path = os.path.join("client_certificates")
        cert = open(path+"/ECs de Autenticação/"+cert+".cer", 'rb').read()

        # Start chain
        chain = []

        # Get issuer
        issuer = self.get_issuer(cert)

        trusted_certs = [
            f 
            for f in os.listdir("client_certificates") 
            if os.path.isfile(os.path.join("client_certificates", f))
        ]
        
        while True:
            try:
                with open(os.path.join(path, issuer+".cer"), 'rb') as f:
                    chain.append(f.read())
            except FileNotFoundError:
                with open(os.path.join(path, "ECs de Autenticação/" +issuer+".cer"), 'rb') as f:
                    chain.append(f.read())
            
            cert = chain[-1]
            
            issuer = self.get_issuer(cert)
            if issuer == self.get_subject(cert):
                break

        return chain


    # Get the issuer of a given certificate
    def get_issuer(self, cert):
        certificate = x509.load_der_x509_certificate(cert, default_backend())
        issuer = certificate.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        return issuer


    # Get the subject of a given certificate
    def get_subject(self, cert):
        certificate = x509.load_der_x509_certificate(cert, default_backend())
        subject = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        return subject   


    # Get the certificate of the type in args
    def get_certificate(self,typeOfCert):
        session = self.PKCS11_session
        certHandle = session.findObjects(
            [(CKA_CLASS, CKO_CERTIFICATE),
            (CKA_LABEL, 'CITIZEN ' + str(typeOfCert) + ' CERTIFICATE')]
        )[0]
        return bytes(session.getAttributeValue( certHandle, [CKA_VALUE], True )[0])


    # Sign a message with the private citizen authentication key
    def sign(self, msg_fields=[]):
        hashing = hashes.Hash(hashes.SHA1(), default_backend())
        for field in msg_fields:
            hashing.update(field.encode())
    
        digest = hashing.finalize()

        if self.PKCS11_session is not None:
            try:
                label = "CITIZEN AUTHENTICATION KEY"
                priv_k = self.PKCS11_session.findObjects([(CKA_CLASS, CKO_PRIVATE_KEY), (CKA_LABEL, label)])[0]
                mechanism = PyKCS11.Mechanism(CKM_SHA1_RSA_PKCS)
                return bytes(self.PKCS11_session.sign(priv_k, digest, mechanism))
            except PyKCS11.PyKCS11Error as e:
                print("Could not sign the message: ", e )
            except IndexError:
                print( "CITIZEN AUTHENTICATION PRIVATE KEY not found\n" )


    # Verify a certificate and its chain
    def validate_cert(self, certificate, chain):
        # Check if certificate is in trusted certificates list
        # Transform bytes into certificate
        cert = x509.load_der_x509_certificate(certificate, default_backend())
        cert_name = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value+".cer"

        # Get list of trusted certifiates by the client        
        trusted_certs = [
            f 
            for f in os.listdir("client_trusted_certificates") 
            if os.path.isfile(os.path.join("client_trusted_certificates", f))
        ]
        
        if cert_name in trusted_certs:
            with open(os.path.join("client_trusted_certificates", cert_name),"rb") as f:
                if cert == x509.load_der_x509_certificate( f.read(), default_backend() ):
                    print(" > CERTIFICATE \'{}\' IS VALID".format(cert_name))
                    return True # Only need the lowest trusted

        # Verify the chain
        if len(chain) != 0:
            try:
                return self.validate_cert(chain[0],chain[1:])
            except Exception as e:
                raise Exception(e)

