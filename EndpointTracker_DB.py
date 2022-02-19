"""
    Este programa crea una base de datos para recolectar la siguiente informacion
    de los dispositivos que están en el vManage:

    Hostaname, System IP, Estado del Tack, Template id, UUID

    Esta informacion la usaremos para el programa 'track_dia.py'.

    Cada vez que se ejecute este programa realizara la siguiente acción:

    Si no existe una base de datos: 
        se creará.
     Si existe la base de datos:
        el programa la actualizara con la informacion
        obtenida del vManage
"""

import os
from token_vmanage import get_token
import sqlite3 as sql
from  datetime import datetime
from pprint import pprint
import json
import requests
import getpass
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

disable_warnings(InsecureRequestWarning)

vmanage = os.environ.get("VMANAGE")
username = os.environ.get("USERNAME_VMANAGE")
password = os.environ.get("PASSWORD_VMANAGE")

def db_decorator(function):
    def decorator_function(*args, **kwargs):
        ########Create DB##########
        conn = sql.connect("EndpointTracker_State.db")
        global cursor
        cursor = conn.cursor()

        crear = function(*args, **kwargs)

        conn.commit()
        conn.close()

        return crear

    return decorator_function

@db_decorator
def db_create():

    ########Create Table##########
    cursor.execute(
        """CREATE TABLE EndpointTracker_State (
            Device text,
            SystemIP text,
            State text,
            TemplateId text,
            UUID text
        )"""
    )

    return "DB creada con exito"

@db_decorator
def insert_data_db(list_device):

    #######Insert Row##########()
    instruccion = f"INSERT INTO EndpointTracker_State VALUES (?,?,?,?,?)"
    cursor.executemany(instruccion, list_device)

    return "Data insertada con exito en la DB"

def device_info(vmanage, headers):
    """
    Función para obtener la informacion que necesitamos de los equipos 
    y crear la base de datos. Esta función retornara una Lista.
    """

    url = f"https://{vmanage}:8443/dataservice/system/device/vedges"
    response = requests.request("GET", url, headers=headers, data={}, verify=False)

    if response.ok:
        data_get_json = json.loads(response.text)
        device_info_table = []
        list_delete_deviceId = []
        print("Inicio proceso de obtención de datos...")

        for data in data_get_json['data']:
            try:
                hostname = data['host-name']
                deviceIP = data['system-ip']
                deviceId = data['uuid']
                templateId = data['templateId']

                url = f"https://{vmanage}:8443/dataservice/device/endpointTracker?deviceId={deviceIP}"
                response =  requests.request("GET", url, headers=headers, data={}, verify=False)

                if response.ok:
                    data_json = json.loads(response.text)
                    if  data_json['data']:
                        state_track = data_json['data'][0]['state']

                    else:
                        state_track = "N/A"

                    device_info_table.append((hostname, deviceIP, state_track, templateId, deviceId))

                else:
                    print(response.text)
            
            except KeyError as e:
                """
                Si se genera un error es porque el equipo 
                se encuentra en la lista de dispositivo del vManage, 
                pero aún no en operación o se ha dado de baja.
                El UUID se almacenará en una lista para validar 
                si se encuentra en la base de datos y poderlo eliminar.
                """
                # e = str(e)
                # if e == "'templateId'":
                #     templateId = "--"
                #     device_info_table.append((hostname, deviceIP, state_track, templateId, deviceId))
                if e == "'host-name'":
                    deviceId = data['uuid']
                    list_delete_deviceId.append(deviceId)
                    # with open(r"keyerror_db.txt", 'a') as f:
                    #     f.write(f"{e}  {deviceId}\r\n")
                continue

    else:
        print(response.text)

    return device_info_table, list_delete_deviceId

@db_decorator
def read_data_base():
    #########read DB##########

    cursor.execute("SELECT * FROM EndpointTracker_State")
    datos = cursor.fetchall()

    return datos

@db_decorator
def update_data_base(hostname, deviceIP, state_track, templateId, deviceId):
    #########update DB##########

    cursor.execute(f"""
                        UPDATE EndpointTracker_State 
                        SET Device='{hostname}', SystemIP='{deviceIP}', State='{state_track}', TemplateId='{templateId}' 
                        WHERE  UUID='{deviceId}'
                    """)

    return "DB actualizada!!!"

@db_decorator
def delete_data_base(uuid):
    ######## DELETE ROW #########

    cursor.execute(f"DELETE FROM EndpointTracker_State WHERE UUID='{uuid}'")

    return f"Se elimino el uuid {uuid} de la base de datos, porque ya no tiene información."

if __name__ == '__main__':
 
    try:

        # vmanage = input("\nvManage: ")
        # username = input("\nUsername: ")
        # password = getpass.getpass("Password: ")
        # print("\n")

        # Funcion con la que obtenemos el token para poderlo usar en los request
        headers = get_token(username, password, vmanage)

        start_time = datetime.now()

        """
        Crear DB. Si ya exixte, mostrar en pantalla mensaje que ya existe una DB creada
        """
        try:
            listas = device_info(vmanage, headers)
            list_device = listas[0]
            list_delete_deviceId = listas[1]

            # Crearemos e insertaremos la informacion de la lista en la DB.
            print(db_create())
            print(insert_data_db(list_device))

        except sql.OperationalError as e:
            """ La excepción se genera cuando la base de datos existe"""
            print(e)

            # Se eliminara de la DB los UUID que ya no tienen info en el vManage
            for deviceId in list_delete_deviceId:
                for itms in read_data_base():
                    uuid = itms[4]
                    if uuid == deviceId:
                        print(delete_data_base(uuid))
                else:
                    continue

            """
            Tomaremos la informacion traida del vManage de cada dispositivo, 
            la cual usaremos para comparar con la informacion de la DB.
            Si el device no esta en la DB, agregarlo.
            """
            for data in list_device:
                hostname = data[0]
                deviceIP = data[1]
                state_track = data[2]
                templateId = data[3]
                deviceId = data[4]

                """
                Leemos la base de datos para comparar la informacion que tenemos ahí,
                con la que traemos del vManage y actualizarla. 
                """
                datos = read_data_base()
                for itms in datos:
                    systemip = itms[1]
                    uuid = itms[4]

                    if deviceId == uuid:
                        update_data_base(hostname, deviceIP, state_track, templateId, deviceId)
                        break

                else:
                    lista = []
                    lista.append((hostname, deviceIP, state_track, templateId, deviceId))
                    print(insert_data_db(lista))
            print("DB actualizada!!!")

        end_time = datetime.now()
        print(f"Total time: {end_time - start_time}")

    except KeyboardInterrupt as e:
        print(e)
