
import os 
  
def fix():
	directories = [
		"client_trusted_certificates",
	]

	for d in directories:
		if os.path.isdir(d):
		    for filename in os.listdir(d): 
		        src = filename
		        dst = src
				dst = dst.replace("ECRaizEstado-self.cer", "ECRaizEstado.cer")
		        dst = dst.replace("idadao","idadão")
		        dst = dst.replace("artao","artão")
		        os.rename(
		            d+"/"+src,
		            d+"/"+dst
		        )

fix()
