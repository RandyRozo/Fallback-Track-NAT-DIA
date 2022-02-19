import requests
import getpass
import json
import sys
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

disable_warnings(InsecureRequestWarning)


def autentication(username, password, vmanage):

	url = f"https://{vmanage}:8443/j_security_check"

	payload={
		'j_username': username,
		"j_password": password
		}

	try:
		response = requests.request("POST", url, data=payload, verify=False)
	except Exception as e:
		print(e)
		exit()

	try:
		cookies = response.headers["Set-Cookie"]
		jsessionid = cookies.split(";")
		return(jsessionid[0])
	except:
		print("No valid JSESSION ID returned\n")
		exit()

def get_token(username, password, vmanage):

	cookie = autentication(username, password, vmanage)
	headers = {"Cookie": cookie}

	url = f"https://{vmanage}:8443/dataservice/client/token"

	response = requests.request("GET", url, headers=headers, verify=False)

	if response.ok:

		token = response.text
		headers = {'Content-Type': "application/json",'Cookie': cookie,'X-XSRF-TOKEN': token}
		return headers
	else:
		None


if __name__ == '__main__':
	vmanage = input("\nvManage: ")
	username = input("\nUsername: ")
	password = getpass.getpass("Password: ")
	print(get_token(username, password,vmanage))
