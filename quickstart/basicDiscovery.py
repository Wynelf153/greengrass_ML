import os
import sys
import time
import uuid
import json
import logging
import argparse

from PIL import Image
from datetime import datetime

#to json serialize the images from camera
import numpy as np
import codecs, json 

import cv2

from AWSIoTPythonSDK.core.greengrass.discovery.providers import DiscoveryInfoProvider
from AWSIoTPythonSDK.core.protocol.connection.cores import ProgressiveBackOffCore
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from AWSIoTPythonSDK.exception.AWSIoTExceptions import DiscoveryInvalidRequestException
# General message notification callback
def customOnMessage(message):
    print('Received message on topic %s: %s\n' % (message.topic, message.payload))

MAX_DISCOVERY_RETRIES = 10
GROUP_CA_PATH = "./groupCA/"

#entire file names of 

host 		= 							#AWS IoT endpoint (see AWS IOT Greengrass Developer Guide, Module 4, Test Communications to find)
rootCAPath 	= 							#name of the root path        (usually root.ca.pem)
certificatePath = 							#name of the certificate file (cert.pem)
privateKeyPath 	= 							#name of the private key file (private.key)
clientId 	= 							#name of device from the aws gui
thingName 	= 							#name of device from the aws gui
topic 		= 							#name of subscription topic sending MQTT messages from greengrass device to greengrass core lambda
message		= ''							#not relevant
port 		= 8883							#default port is 8883

#Error messages if credentials, certificates etc missing

if not certificatePath or not privateKeyPath:
    print("Missing credentials for authentication, you must specify --cert and --key args.")
    time.sleep(1)
    exit(2)

if not os.path.isfile(rootCAPath):
    print("Root CA path does not exist {}".format(rootCAPath))
    time.sleep(1)
    exit(3)

if not os.path.isfile(certificatePath):
    print("No certificate found at {}".format(certificatePath))
    time.sleep(1)
    exit(3)

if not os.path.isfile(privateKeyPath):
    print("No private key found at {}".format(privateKeyPath))
    time.sleep(1)
    exit(3)

# Configure logging
logger = logging.getLogger("AWSIoTPythonSDK.core")
logger.setLevel(logging.DEBUG)
streamHandler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

# Progressive back off core
backOffCore = ProgressiveBackOffCore()

# Discover GGCs
discoveryInfoProvider = DiscoveryInfoProvider()
discoveryInfoProvider.configureEndpoint(host)
discoveryInfoProvider.configureCredentials(rootCAPath, certificatePath, privateKeyPath)
discoveryInfoProvider.configureTimeout(10)  # 10 sec

retryCount = MAX_DISCOVERY_RETRIES
discovered = False
groupCA = None
coreInfo = None
while retryCount != 0:
    try:
        discoveryInfo = discoveryInfoProvider.discover(thingName)
        caList = discoveryInfo.getAllCas()
        coreList = discoveryInfo.getAllCores()

        # We only pick the first ca and core info
        groupId, ca = caList[0]
        coreInfo = coreList[0]
        print("Discovered GGC: %s from Group: %s" % (coreInfo.coreThingArn, groupId))

        print("Now we persist the connectivity/identity information...")
        groupCA = GROUP_CA_PATH + groupId + "_CA_" + str(uuid.uuid4()) + ".crt"
        if not os.path.exists(GROUP_CA_PATH):
            os.makedirs(GROUP_CA_PATH)
        groupCAFile = open(groupCA, "w")
        groupCAFile.write(ca)
        groupCAFile.close()

        discovered = True
        print("Now proceed to the connecting flow...")
        break
    except DiscoveryInvalidRequestException as e:
        print("Invalid discovery request detected!")
        print("Type: %s" % str(type(e)))
        print("Error message: %s" % e.message)
        print("Stopping...")
        break
    except BaseException as e:
        print("Error in discovery!")
        print("Type: %s" % str(type(e)))
        print("Error message: %s" % e.message)
        retryCount -= 1
        print("\n%d/%d retries left\n" % (retryCount, MAX_DISCOVERY_RETRIES))
        print("Backing off...\n")
        backOffCore.backOff()

if not discovered:
    print("Discovery failed after %d retries. Exiting...\n" % (MAX_DISCOVERY_RETRIES))
    sys.exit(-1)

# Iterate through all connection options for the core and use the first successful one
myAWSIoTMQTTClient = AWSIoTMQTTClient(clientId)
myAWSIoTMQTTClient.configureCredentials(groupCA, privateKeyPath, certificatePath)
myAWSIoTMQTTClient.onMessage = customOnMessage

connected = False
for connectivityInfo in coreInfo.connectivityInfoList:
    currentHost = connectivityInfo.host
    currentPort = connectivityInfo.port
    print("Trying to connect to core at %s:%d" % (currentHost, currentPort))
    myAWSIoTMQTTClient.configureEndpoint(currentHost, currentPort)
    try:
        myAWSIoTMQTTClient.connect()
        connected = True
        break
    except BaseException as e:
        print("Error in connect!")
        print("Type: %s" % str(type(e)))
        print("Error message: %s" % e.message)

if not connected:
    print("Cannot connect to core %s. Exiting..." % coreInfo.coreThingArn)
    sys.exit(-2)

#send pictures to core lambda

vc = cv2.VideoCapture(0)
#let camera autocapture
time.sleep(1)
rval, frame = vc.read()

#picture path is where the physical device stores pictures it captures from the webcam
picture_path = ""

while True:
    rval, frame = vc.read()

    #use timestamp as part of name picture stored on the physical device
    now = str(datetime.now().timestamp())
    now = now.replace('.', '_')

    filename = os.path.join(picture_path, f"godwyn_cam_{now}.jpg")         

    #save frame as image file
    im = Image.fromarray(frame)
    im.save(filename)

    #json's format --> {'filename': *actual_file_name*, 'message':*redundant message*}
    message = {}
    message['filename'] = f'godwyn_cam_{now}.jpg' #'hi from the device'
    message['message'] = f'Added a {filename} to the directory!'
    messageJson = json.dumps(message)
    myAWSIoTMQTTClient.publish(topic, messageJson, 0)
