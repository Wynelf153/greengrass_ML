from gluoncv import model_zoo, data, utils
import cv2
import time
import gluoncv as gcv
import numpy as np
import mxnet
import boto3
import os
import json

duration = 120

# In[10]:

#path where model data will be stored after downloaded from AWS S3
model_path = '/home/godwyn/Documents/greengrass_models'

object_string = os.environ['objects'].lower()
objects = object_string.split('_')
    
s3 = boto3.client('s3')
iot_client = boto3.client('iot-data')

#class of model
classes = ('aeroplane', 'bicycle', 'bird', 'boat', 'bottle', 'bus', 'car', 'cat', 'chair', 'cow', 'diningtable', 'dog', 'horse', 'motorbike', 'person', 'pottedplant', 'sheep', 'sofa', 'train', 'tvmonitor')

#model data consists of two files, xxx-symbol.json and xxx-0000.params
#in this case, the files are named cat_model_test-symbol.json, cat_model_test-0000.params etc, can be changed
json_s3_list   = [f'{object}_model_test-symbol.json' for object in objects]
params_s3_list = [f'{object}_model_test-0000.params' for object in objects]

#creating OS path for where the model json and param will be stored after download
json_path_list = [os.path.join(model_path, f'{object}_model_test.json') for object in objects]
params_path_list = [os.path.join(model_path, f'{object}_model_test.params') for object in objects]

s3 = boto3.client('s3')

#download model params and json using list comprehension
_ = [s3.download_file('greengrassmodels', json_s3, json_path) for json_s3, json_path in zip(json_s3_list, json_path_list)]
_ = [s3.download_file('greengrassmodels', params_s3, params_path) for params_s3, params_path in zip(params_s3_list, params_path_list)]

ctx = mxnet.gpu() if mxnet.context.num_gpus() else mxnet.cpu()

#reconstruct models from component
net_list = [mxnet.gluon.nn.SymbolBlock.imports(json_path, ['data'], params_path, ctx=ctx) for json_path, params_path in zip(json_path_list, params_path_list)]

#lambda will upload picture to S3 if model says probability of target object appearing is larger than the threshold. 
threshold = 0.2

#path where the greengrass device stored the pictures
picture_folder_path = "/greengrass_device_send_pictures/pictures"

def run_model(filename, objects):
    
    #get frame here
    picture_path = os.path.join(picture_folder_path, filename)

    frame = cv2.imread(picture_path)

    os.remove(picture_path)    

    #process frame such that it is readable by model
    frame = mxnet.nd.array(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).astype('uint8')
    rgb_nd, frame = gcv.data.transforms.presets.ssd.transform_test(frame, short=512, max_size=700)

    # Run frame through network

    #returns [[class_IDs_0, scores_0, bounding_boxes_0], [class_IDs_1, scores_1, bounding_boxes_1], ...]
    results = [net(rgb_nd) for net in net_list]

    #getting model results from the output matrix
    target_class_index_list = [classes.index(object) for object in objects]

    placeholder = [results[i][0][0].asnumpy().tolist() for i in range(len(objects))]
    class_IDs_list = [[int(x[0]) for x in placeholder_element] for placeholder_element in placeholder]
    
    placeholder = [results[i][1][0].asnumpy().tolist() for i in range(len(objects))]
    scores_list = [[x[0] for x in placeholder_element] for placeholder_element in placeholder]
    
    zero_list = [0 for item in target_class_index_list]    

    #check if the detection result contains query objects
    checklist = [target_class_index_element in class_ID_element for target_class_index_element, class_ID_element in zip(target_class_index_list, class_IDs_list)]
    
    if False not in checklist:
        #if probability (by model) < threshold, set probability to 0. Otherwise, probability is that given by the model
        probability_list = [scores_list[i][class_IDs_list[i].index(target_class_index_list[i])] if scores_list[i][class_IDs_list[i].index(target_class_index_list[i])] > threshold else 0 for i in range(len(objects))]
    else:
        probability_list = zero_list

    if 0 in probability_list:
        return 0, frame
    else:
        return probability_list, frame


def s3_upload(frame, filename):
    #upload frame to s3
    image_string = cv2.imencode('.jpg', frame)[1].tobytes()
    s3.put_object(Bucket="publicbucketfortesting", Key = f"camera_g_{filename}.jpg", Body=image_string)
    return

def lambda_handler(event, context):
    filename = event['filename']

    probability, frame = run_model(filename, objects)
    if probability:
        s3_upload(frame, filename)
    #debug stuff
    iot_client.publish(topic = 'dummy/test', qos = 0, payload = json.dumps({'object':str(objects)}))
    return {'object':objects} 
