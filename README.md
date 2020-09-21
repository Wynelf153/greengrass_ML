# Setting up the Greengrass Group
This guide assumes that the user is using a linux device with a webcam, python3.7 is downloaded and the user has root privileges.
## 1. Create an AWS Greengrass Group
Log into your AWS account, go to the IOT console and create a greengrass group. Use default creation, and save the keys and certs. Further instructions can be found here: 
https://docs.aws.amazon.com/greengrass/latest/developerguide/gg-config.html

## 2. Download AWS Core Software
Log into the AWS console, and retrieve your AWS Access Key ID and your AWS Secret Key ID at IAM. Then, install the AWS Greengrass Core Software.
```
wget -q -O ./gg-device-setup-latest.sh https://d1onfpft10uf5o.cloudfront.net/greengrass-device-setup/downloads/gg-device-setup-latest.sh && chmod +x ./gg-device-setup-latest.sh && sudo -E ./gg-device-setup-latest.sh bootstrap-greengrass-interactive
```
When prompted, enter your Key ID details and your region. (If unsure of what region to enter, us-east-2 seems to work fine.)

## 3. Replace certs and modify config file
Assuming greengrass is installed at the default location, move the certificates and key files downloaded to ```/greengrass/certs```.
```
sudo cp -a /path/to/created/groups/certs. /greengrass/certs/
```
Then, edit the config file to match the name of the downloaded certificates.
```
sudo nautilus 
```
Edit the values of ```caPath```, ```certPath```, ```keyPath``` in the json to the file names of the files downloaded in step 1. Also edit the name of the group core to match that created in step 1.

## 5. Create deploy package
Create a folder ```deployment_package``` to contain the libraries and code used in the lambda.
```
sudo mkdir Desktop/deployment_package
```
Install ```Mxnet``` onto the local device’s python. 
```
sudo python3.7 -m pip install mxnet
```
Install the python libraries used in the lambda function into the deployment_package folder
```
sudo python3.7 -m pip install --target=Desktop/deployment_package gluoncv
sudo python3.7 -m pip install --target=Desktop/deployment_package numpy
sudo python3.7 -m pip install --target=Desktop/deployment_package pillow
sudo python3.7 -m pip install --target=Desktop/deployment_package opencv-python==4.2.0.34
```
And remove unused library files to make sure the lambda deployment package stays under the size limit of 250 MB.
```
sudo rm -r Desktop/deployment_package/matplotlib Desktop/deployment_package/matplotlib-3.3.2.dist-info Desktop/deployment_package/mpl_toolkits
```
Next, download the ```lambda_function.py``` file, and move it into the deployment_package folder.
```
cd Desktop
sudo git clone https://github.com/Wynelf153/greengrass_ML.git
cd
sudo mv Desktop/greengrass_ML/quickstart/lambda_function.py Desktop/deployment_package
```
Modify the paths of the variables ```model_path``` at line 16 of ```lambda_function.py```,
```
model_path = ‘Desktop/model_json_params’
```
that of the variable ```picture_folder_path``` at line 51 of ```lambda_function.py```,
```
picture_folder_path = ‘Desktop/webcam_pictures’
```
and also the name of your S3 bucket, which will be created in step 6 to store pictures containing the images with the query objects, at line 100 of ```lambda_function.py```,
```
s3.put_object(Bucket="objectfoundwebcampictures", Key = f"camera_g_{filename}.jpg", Body=image_string)
```
Now, create two folders, one to store parameters of ML models and one to store pictures taken by the webcam.
```
sudo mkdir Desktop/model_json_params
sudo mkdir Desktop/webcam_pictures
```
and finally zip the contents of the ```deployment_package``` folder (Not the folder itself)
```
cd ~/Desktop/deployment_package
zip -r deployment_package.zip
```

## 6. Manage S3 Folders and upload deployment package
Log in to the AWS console and navigate to S3. Create a bucket, name it with the name given to the bucket in ```lambda_function.py``` in step 5, (e.g. ```objectfoundwebcampictures```).
Create another bucket named ```greengrassmodels``` (if you name it differently modify line 39, 40 of ```lambda_function.py``` accordingly and rezip the deployment_package) and upload the test model’s corresponding .json and .params file into that bucket, naming the files ```[object]_model_test-symbol.json``` and ```[object]_model_test-0000.params``` respectively. These files should be located at ```Desktop/greengrass_ML/test_model```.

Reupload a set of .json and .params files for every object you wish to detect. For instance, if you wish to detect people and water bottles, upload each of the ```.json``` and ```.params files``` twice, naming them ```person_model_test-symbol.json```, ```person_model_test-0000.params```, ```bottle_model_test-symbol.json```, ```bottle_model_test-0000.params etc```. The test model can detect the following objects: 
```
classes = ('aeroplane', 'bicycle', 'bird', 'boat', 'bottle', 'bus', 'car', 'cat', 'chair', 'cow', 'diningtable', 'dog', 'horse', 'motorbike', 'person', 'pottedplant', 'sheep', 'sofa', 'train', 'tvmonitor')
```

Upload the ```deployment_package.zip``` file (normally located at ```Desktop/deployment_package/deployment_package.zip```) to the greengrassmodels bucket, or any other bucket. Click on the zip in the S3 GUI once the file has finished uploading, and copy the link displayed.


## 7. Create lambda in AWS lambda GUI
Log in to the AWS console and navigate to IAM. Click on Access Management on the left bar, then the Policies section. Click Create Policy, then copy and paste the following json into the json tab at the very top.
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "iot:Publish"
            ],
            "Resource": [
                "*"
            ]
        }
    ]
}
```
Once that is done, click on review policy, name the policy ```UploadToMQTT``` and click on Create Policy.


Then, click the Roles section. On the very top of the page, click Create Role. 

Select AWS Service under “Select type of trusted entity”.
Under “Choose a use case”, select lambda. After this has been done, click Next: Permissions.
In filter policies, search for ```AWSLambdaBasicExecutionRole``` and tick the box to the very left. Repeat this step for the policies ```AmazonS3FullAccess``` and ```UploadToMQTT```.  Click on Next: Tags, then Next: Review. Name the newly created role ```detectionLambdaRole```. This role will be given to the AWS Lambda during creation.

Then, create another role. Select AWS Service, then Greengrass under “Choose a use case”. Similar to the previouos role, select the policies ```AWSLambdaBasicExecutionRole```, ```AmazonS3FullAccess``` and ```UploadtoMQTT```, then name the role ```detectionLambdaGroupRole```. This role will be given to the Greengrass Group to ensure the lambda running on the AWS Greengrass Core Device has sufficient permissions.

Once the roles have been created, navigate to AWS Lambda, and create a function. Name the function ```detectionLambda```, and choose python3.7 as the runtime. On the bottom of the screen, change the Default Execution Role, and use the existing role ```detectionLambdaRole``` then create the function. It may take a few minutes to assign ```detectionLambdaRole``` to the lambda since it was newly created.

Once the function has been created, under function code, click Actions and then Upload a File from Amazon S3. Paste in the link of ```deployment_package.zip``` copied earlier. 

On the top bar, create a new version of the function with description 0, and create an alias alias_0 corresponding to version 0.

## 8. Set up AWS Greengrass Device.
*Do not confuse AWS Greengrass Device with AWS Greengrass Core Device.*

Create an empty folder send_pictures, where the certs and script of the AWS Greengrass Device will be stored.
```
sudo mkdir /send_pictures
```
In the Greengrass Group created in Step 1, choose Devices, then create a device. Name the device ```send_pictures```, and download the keys and certificates into the ```/send_pictures``` folder. Also move the ```basicDiscovery.py``` file into the send_pictures folder.
```
sudo mv path/to/device/certs/or/keys /send_pictures
sudo mv Desktop/greengrass_ML/basicDiscovery.py /send_pictures
```
In ```basicDiscovery.py```, fill in lines 47-55 and modify line 173 to point ```picture_path``` to point to the actual folder path, similar to that in step 5.
```
picture_path = "Desktop/webcam_pictures"
```
## 9. Setup group and deploy

Open up the Greengrass Group’s page created in Step 1. 

In Lambda, add ```detectionLambda.py``` to the group. Edit the configuration of the lambda as follows:
```
Run as → Another user ID/ group ID → UID:0 , GID:0
Containerization: No container
Timeout: 600 seconds 
Input payload type: JSON
Environment variables → Key: Objects → Value: (Objects you want to detect separated by a comma, e.g. person,bottle/ car,aeroplane)
```
If using the default model, classes that can be tested include:
```
classes = ('aeroplane', 'bicycle', 'bird', 'boat', 'bottle', 'bus', 'car', 'cat', 'chair', 'cow', 'diningtable', 'dog', 'horse', 'motorbike', 'person', 'pottedplant', 'sheep', 'sofa', 'train', 'tvmonitor')
```

Then click update.

In Subscriptions, create a new subscription with Source: ```send_pictures``` (device) and target: ```DetectionLambda:alias_0```. Set the Topic to ```send_pictures/topic_1```. 

Lastly, under settings, add the "detectionLambdaGroupRole" to the Group.

Now that the group has been configured, open up a new terminal on your device and start the greengrass core software -
```
cd /greengrass/ggc/core/
sudo ./greengrassd start
```
Once the AWS Greengrass Core software has been started, navigate back to the AWS Greengrass GUI and deploy the group.

*Error logs for running ```detectionLambda.py``` should be under ```/greengrass/ggc/var/log/user/us-xxx-x/xxxxxxxxxxxx```. If you cannot find the logs for the lambda runtime and ```/greengrass/ggc/var/log/user``` does not exist, consider navigating to ```/greengrass/ggc/var/log``` and create an empty folder ```/user```*


## 10. Start the send_pictures device’s script.
Open up a new terminal, and start the send_pictures device's script.
```
cd /send_pictures
sudo python3.7 basicDiscovery.py
```

*Before starting the script, make sure you have your target objects ready to go, no other appliance is using the camera and that the greengrass core software has been started and the group deployed.*
