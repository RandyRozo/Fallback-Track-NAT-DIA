import os
import time
import getpass
from  datetime import datetime
import json
import requests
from netmiko import ConnectHandler, redispatch
import logging
import sqlite3 as sql
from token_vmanage import get_token
from EndpointTracker_DB import  read_data_base
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

disable_warnings(InsecureRequestWarning)


url_teams = os.environ.get("URL_TEAMS")
roomID = os.environ.get("ROOMID")
access_token_wb = os.environ.get("ACCESS_TOKEN_WB")
vmanage = os.environ.get("VMANAGE")
username = os.environ.get("USERNAME_VMANAGE")
password = os.environ.get("PASSWORD_VMANAGE")
password_devices = os.environ.get("PASSWORD_DEVICES")


def update_data_base(deviceIP, state_track):
    #########update DB##########

    conn = sql.connect("EndpointTracker_State_v3.db")
    cursor = conn.cursor()

    cursor.execute(f"""
            UPDATE EndpointTracker_State 
            SET State='{state_track}' 
            WHERE  SystemIP='{deviceIP}'
        """)

    conn.commit()
    conn.close()

    print("DB actualizada!!!")


def device_info(vmanage, headers):

    url = f"https://{vmanage}:8443/dataservice/system/device/vedges"
    response = requests.request("GET", url, headers=headers, data={}, verify=False)

    if response.ok:
        data_get_json = json.loads(response.text)
        device_info_table = []
        
        for data in data_get_json['data']:
            try:
                hostname = data['host-name']
                deviceIP = data['system-ip']
                templateId = data['templateId']
                deviceId = data['uuid']

                url = f"https://{vmanage}:8443/dataservice/device/endpointTracker?deviceId={deviceIP}"
                response =  requests.request("GET", url, headers=headers, data={}, verify=False)

                if response.ok:
                    data_json = json.loads(response.text)
                    if  data_json['data']:
                        state = data_json['data'][0]['state']

                    else:
                        state = "N/A"

                    device_info_table.append((hostname, deviceIP, state, templateId, deviceId))

                else:
                    print(response)
            except KeyError:
                continue
    else:
        print(response)
    return device_info_table


def get_endpointTracker(deviceIP, vmanage, headers):

    url = f"https://{vmanage}:8443/dataservice/device/endpointTracker?deviceId={deviceIP}"
    response =  requests.request("GET", url, headers=headers, data={}, verify=False)

    if response.ok:
        data_get_json = json.loads(response.text)

        if  data_get_json['data']:
            state_track = data_get_json['data'][0]['state']

        else:
            state_track = "N/A"

        return state_track

    else:
        print(response)


def detach_device(deviceIP, deviceId, vmanage, headers):

    print(f"Changing device {deviceIP} configuration mode to CLI")
    url = f"https://{vmanage}:8443/dataservice/template/config/device/mode/cli"
    payload={
        "deviceType": "vedge",
        "devices": [
            {
                "deviceId": deviceId,
                "deviceIP": deviceIP
            }
        ]
    }
    session = json.dumps(payload, indent=1)
    response = requests.request("POST", url, headers=headers, data=session, verify=False)

    if response.ok:
        data_post_json = json.loads(response.text)
        id_response = data_post_json["id"]
    else:
        print(response)

    status = "in_progress"
    while status == "in_progress":

        url = f"https://{vmanage}:8443/dataservice/device/action/status/{id_response}"
        response =  requests.request("GET", url, headers=headers, data={}, verify=False)
        if response.ok:
            data_get_json = json.loads(response.text)
            status = data_get_json["summary"]["status"]
            print(status)

        else:
            print(response)

    return id_response


def delete_config(vmanage, username, password, deviceIP, password_devices):

    #logging.basicConfig(filename='cedge_basic.log', level=logging.DEBUG)
    #logger = logging.getLogger("netmiko")
    print("Iniciando proceso para eliminar el 'ip nat route' del dispositivo")
    login = {
        'device_type' : 'linux',
        'host' : vmanage,
        'username' : username,
        'password' : password,
        'port' : 19001
    }

    net_connect = ConnectHandler(**login)
    net_connect.enable()

    # para conectarce al dispositivo tomara el mismo usuario del vManage
    comands = f"request execute vpn 0 ssh {deviceIP} -p830\n"
    net_connect.write_channel(comands)
    time.sleep(1)
    prompt = net_connect.read_channel()

    if "fingerprint" in prompt:
        net_connect.write_channel("yes\n")
        time.sleep(1)
        prompt = net_connect.find_prompt()

    while "assword:" in prompt:
        net_connect.write_channel(f"{password_devices}\n")
        time.sleep(2)
        net_connect.write_channel(f"{password_devices}\n")
        prompt = net_connect.find_prompt()
        #print (prompt)

    prompt = net_connect.find_prompt()
    prompt = prompt.replace('#',"")
    #print(prompt)
    redispatch(net_connect, device_type= "cisco_ios" )
    net_connect.config_mode('config-transaction')
    comands = [
       'no ip nat route',
       'commit'  
    ]
    config_commands = net_connect.send_config_set(comands)
    #config_commands = net_connect.send_command('show sdwan running-config')
    #print(config_commands)
    net_connect.disconnect()


def attach_device(vmanage, headers, deviceId, templateId):

    #  Proceso  para  generar  input  de  la  configuracion
    print(f"Configuring device {deviceIP} with feature template")
    url = f"https://{vmanage}:8443/dataservice/template/device/config/input"

    payload= {
        "templateId": f"{templateId}",
        "deviceIds":
            [
            f"{deviceId}"
            ],
        "isEdited":False,
        "isMasterEdited":False
        }

    session = json.dumps(payload, indent=1)
    response = requests.request("POST", url, headers=headers, data=session, verify=False)
    if response.ok:
        data_post_json = json.loads(response.text)
        config = data_post_json["data"][0]
        #print(config)
    else:
        print(response.text)

    #  Proceso  para  generar  vista  previa  de  la  configuracion

    url = f"https://{vmanage}:8443/dataservice/template/device/config/config"

    payload={
            "templateId":f"{templateId}",
            "device": config,
            "isEdited":False,
            "isMasterEdited":False
            }

    session = json.dumps(payload, indent=1)
    response = requests.request("POST", url, headers=headers, data=session, verify=False)
    if response.ok:
        data = response.text
        #print(data)
    else:
        print(response.text)


    #  Proceso  para  attach  divece  template

    url = f"https://{vmanage}:8443/dataservice/template/device/config/attachfeature"

    payload = {
                  "deviceTemplateList":[
                  {
                    "templateId":f"{templateId}",       
                    "device":[
                    config
                    ],
                    "isEdited":False,
                    "isMasterEdited":False
                  }
                  ]
                }
    session = json.dumps(payload, indent=1)
    response = requests.request("POST", url, headers=headers, data=session, verify=False)
    if response.ok:
        data_post_json = json.loads(response.text)
        id_response = data_post_json["id"]
        print(id_response)
    else:
        print(response)

    #  Proceso  para  verificar  el  resultado  del  attach
    status = "in_progress"
    while status == "in_progress":
        url = f"https://{vmanage}:8443/dataservice/device/action/status/{id_response}"
        response =  requests.request("GET", url, headers=headers, data={}, verify=False)
        if response.ok:
            data_get_json = json.loads(response.text)
            status = data_get_json["summary"]["status"]
            print(status)
        
        else:
            print(response)
    
    return id_response


def send_message_to_webex(message, learn_more):

    """  Proceso para enviar notificacion a WebexTeam  """

    url = "https://webexapis.com/v1/messages"
    headers_webex = {
                    "Authorization": f"Bearer {access_token_wb}",
                    'Content-Type': "application/json"
        }
    messages = {
                "roomId": roomID,
                "markdown": str(message +'<br> **Details:** ' + learn_more)
    }

    response = requests.request("POST", url, headers=headers_webex, data=json.dumps(messages))
    print(response, "  message sent to Webex")

    """  Proceso para enviar notificacion a Teams  """
    messages_teams = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "",
            "summary": "New Message",
            "sections": [{
                "activityTitle": "",
                "activitySubtitle": message,
                #"text": message,
                #"facts": facts_list,
                "markdown": True
            }],
            "potentialAction": [
                 
            {
                "@type": "OpenUri",
                "name": "Details",
                "targets": [{
                    "os": "default",
                    "uri": learn_more
                }]
            }]
        }

    response = requests.request("POST", url_teams, data=json.dumps(messages_teams))
    print(response, "  message sent to Teams")


if __name__ == '__main__':

    try:

        #vmanage = input("\nvManage: ")
        #username = input("\nUsername: ")
        #password = getpass.getpass("Password: ")

        # Funcion con la que obtenemos el token para poderlo usar en los request
        headers = get_token(username, password, vmanage)

        start_time = datetime.now()

        """
        Realizaremos  la  validacion  del  Track  en  los  equipos
        que  se  encuentran  dentro  de  la  base  de  datos.
        """
        datos = read_data_base()
        for itms in datos:
            hostname = itms[0]
            deviceIP = itms[1]
            state_db = itms[2]
            templateId = itms[3]
            deviceId = itms[4]

            state_track = get_endpointTracker(deviceIP, vmanage, headers)

            message = '''Team, Alarm event : **Tracker State Change** here are the complete details: <br>'''
            values = {
                'Hostname': hostname,
                'SystemIP': deviceIP,
                'State': state_track
                }
            for key, value in values.items():
                message += f'<br> **{key}:** {value}'

            """
            Validamos  el  estado  del  Track,  si  el  estado  es  Down
            se  elimina  la  ruta  defaul  del  NAT  DIA.
            Cuando  vuelva  a  estado  UP  se  vuevle  a  adjuntar  el  Template.
            """
            if state_track == "N/A":
                print (f"El equipo {hostname} No tiene EndpointTracker configurado")
                continue

            elif "down" in state_track and "down" in state_db:
                print (f"No ha cambiado el estdo del EndpointTracker para el dispositivo {hostname}")
                continue

            elif "down" in state_track:
                print (f"Cambiado el estdo del EndpointTracker para el dispositivo {hostname}")
                #message = f"Tracker entry in {hostname} / state => DOWN"
                message += '''<br><br> The device change to **CLI mode** and removed **'ip nat route'** in the config.'''
                #print(message)
                id_response = detach_device(deviceIP, deviceId, vmanage, headers)
                delete_config(vmanage, username, password, deviceIP, password_devices)

                #  Actualizamos el estado del Track en la base de datos
                update_data_base(deviceIP, state_track)
                learn_more = f"https://{vmanage}:8443/#/app/device/status?activity\=device_config_mode_cli&pid={id_response}"

                send_message_to_webex(message, learn_more)

                continue

            elif "up" in state_track and "up" in state_db:
                print (f"No ha cambiado el estdo del EndpointTracker para el dispositivo {hostname}")
                continue

            elif "up" in state_track and "down" in state_db:
                print (f"Cambiado el estdo del EndpointTracker para el dispositivo {hostname}")
                #message = f"Tracker entry in {hostname} / state => UP"
                #print(message)
                if templateId == "--":
                    message += f'''<br><br> The device is **CLI mode** and have push **'ip nat route'** in the config.'''
                else:
                    id_response = attach_device(vmanage, headers, deviceId, templateId)
                    learn_more = f"https://{vmanage}:8443/#/app/device/status?activity=push_feature_template_configuration&pid={id_response}"

                    message += f'''<br><br> The device changed to **vManage mode** and attached Template'''
                update_data_base(deviceIP, state_track)
                send_message_to_webex(message, learn_more)

                continue

        end_time = datetime.now()
        print(f"Total time: {end_time - start_time}")

    except KeyboardInterrupt as k:
        print(k)
    except Exception as e:
        print(e)