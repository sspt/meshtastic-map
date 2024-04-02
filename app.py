import os
import time
from flask import Flask, jsonify, send_from_directory
import paho.mqtt.client as mqtt
import json
import google
from google.protobuf.json_format import MessageToDict
from meshtastic import (admin_pb2,apponly_pb2,deviceonly_pb2,channel_pb2,config_pb2,mesh_pb2,mqtt_pb2,paxcount_pb2,portnums_pb2,remote_hardware_pb2,storeforward_pb2,telemetry_pb2)

MQTT_SERVER = os.environ.get('MQTT_SERVER', 'mqtt.meshtastic.pt')
MQTT_USERNAME = os.environ.get('MQTT_USERNAME', 'meshdev')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD', 'large4cats')
MQTT_TOPIC = os.environ.get('MQTT_TOPIC', 'msh/#')

protobuf_modules = [
    admin_pb2 ,
    apponly_pb2,
    deviceonly_pb2,
    channel_pb2,
    config_pb2,
    mesh_pb2,
    mqtt_pb2,
    paxcount_pb2,
    portnums_pb2,
    remote_hardware_pb2,
    storeforward_pb2,
    telemetry_pb2
]
shared_list = {}

def save():
    print("Saving data")
    with open('data.json', 'w') as f:
        json.dump(shared_list, f)

def load():
    global shared_list
    try:
        with open('data.json', 'r') as f:
            shared_list = json.load(f)
    except FileNotFoundError:
        pass

def decode_message(message):
    try:
        payload = message.payload.decode()
    except UnicodeDecodeError:
        # Not a valid UTF-8 string, try to decode as a Protobuf message
        for module_name in protobuf_modules:
            for class_name in dir(module_name):
                if class_name.startswith('_') or class_name == 'DESCRIPTOR' or class_name.startswith('meshtastic') or class_name == 'str':
                    continue
                try:
                    class_object = getattr(module_name, class_name)

                    msg = class_object()
                    msg.ParseFromString(message.payload)
                    o = MessageToDict(msg, True)

                    
                    newObj = {
                        'type' : 'protobuf',
                        'topic' : message.topic,
                        'qos' : message.qos,
                        'properties' : message.properties,
                        'payload' : o
                    }
                    return newObj
                except google.protobuf.message.DecodeError:
                    pass  # Not a valid Protobuf message for this class, try next class
        # If we get here, the message could not be decoded as a Protobuf message
        raise ValueError('Could not decode message')

    # Try to decode as JSON
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass  # Not JSON, try next format

    # If it's a simple string, return it as a dictionary
    newObj = {
                        'type' : 'internal_text',
                        'sender' : message.topic.split('/')[1],
                        'from' : message.topic,
                        'payload' : payload
                    }
    return newObj
# MQTT message callback
def on_message(client, userdata, message):

    lb = shared_list.__len__()
    try:
        o = decode_message(message)

        if o['type'] == 'protobuf':
            return #For future use
        
        id = str(o['from']) # + str(o['sender'])# gateway + node id (since the node id is only unique across meshes, not globally unique)
        if o['type'] == "nodeinfo" and 'sender' in o:
            print(f"Received nodeinfo from '{id}' : '{o}'")

            # Load previous config
            if id in shared_list:
                newObj = shared_list[id]
                newObj['name'] = o['payload']['longname']
                newObj['last_seen'] = int(time.time() * 1000)
            else:
                shared_list[id] = {
                    'id': id,
                    'name': o['payload']['longname'],
                    'last_seen': int(time.time() * 1000)
                }
        elif o['type'] == "position" and 'sender' in o:
            print(f"Received position from '{id}' : '{o}'")

            # Load previous config
            newObj = {
                'id' : id,
                'last_seen' : int(time.time() * 1000),
                'last_position' : int(time.time() * 1000)
            }
            if id in shared_list:
                if 'lat' in shared_list[id]:
                    newObj['name'] = shared_list[id]['name']
                if 'lat' in shared_list[id]:
                    newObj['lat'] = shared_list[id]['lat']
                if 'lon' in shared_list[id]:
                    newObj['lon'] = shared_list[id]['lon']
                if 'alt' in shared_list[id]:
                    newObj['alt'] = shared_list[id]['alt']
            # Smash with new data
            if 'latitude_i' in o['payload']:
                newObj['lat'] = o['payload']['latitude_i'] / 1e7
            if 'longitude_i' in o['payload']:
                newObj['lon'] = o['payload']['longitude_i'] / 1e7
            if 'altitude' in o['payload']:
                newObj['alt'] = o['payload']['altitude']
            
            shared_list[id] = newObj
        else:
            print(f"Received from '{id}' : '{o['type']} : {o['payload']}'")
            return
        la = shared_list.__len__()
        if lb != la:
            print(f"List length changed from {lb} to {la}")
        save()
    except Exception as e:
        print(f"An error occurred: {e} :: {message}")

# MQTT setup
client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)  # Add this line

client.connect(MQTT_SERVER)  # Replace with your MQTT broker
client.subscribe(MQTT_TOPIC)  # Replace with your MQTT topic
client.loop_start()

# Flask setup
app = Flask(__name__, static_folder='static')

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/nodes')
def nodes():
    return jsonify(shared_list)

if __name__ == '__main__':
    load()
    app.run(host="0.0.0.0",port=80)