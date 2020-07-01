from threading import Thread, Event, Timer
import os
import numpy as np
import json
import awscam
import mo
import greengrasssdk
from local_display import LocalDisplay
import boto3
from cv2 import cv2
import math
import io
from PIL import Image, ImageDraw, ExifTags, ImageColor, ImageFont

class LocalDisplay(Thread):
    """ Class for facilitating the local display of inference results
        (as images). The class is designed to run on its own thread. In
        particular the class dumps the inference results into a FIFO
        located in the tmp directory (which lambda has access to). The
        results can be rendered using mplayer by typing:
        mplayer -demuxer lavf -lavfdopts format=mjpeg:probesize=32 /tmp/results.mjpeg
    """
    def __init__(self, resolution):
        """ resolution - Desired resolution of the project stream """
        # Initialize the base class, so that the object can run on its own
        # thread.
        super(LocalDisplay, self).__init__()
        # List of valid resolutions
        RESOLUTION = {'1080p' : (1920, 1080), '720p' : (1280, 720), '480p' : (858, 480)}
        if resolution not in RESOLUTION:
            raise Exception("Invalid resolution")
        self.resolution = RESOLUTION[resolution]
        # Initialize the default image to be a white canvas. Clients
        # will update the image when ready.
        self.frame = cv2.imencode('.jpg', 255*np.ones([640, 480, 3]))[1]
        self.stop_request = Event()

    def run(self):
        """ Overridden method that continually dumps images to the desired
            FIFO file.
        """
        # Path to the FIFO file. The lambda only has permissions to the tmp
        # directory. Pointing to a FIFO file in another directory
        # will cause the lambda to crash.
        result_path = '/tmp/results.mjpeg'
        # Create the FIFO file if it doesn't exist.
        if not os.path.exists(result_path):
            os.mkfifo(result_path)
        # This call will block until a consumer is available
        with open(result_path, 'wb') as fifo_file:
            while not self.stop_request.isSet():
                try:
                    # Write the data to the FIFO file. This call will block
                    # meaning the code will come to a halt here until a consumer
                    # is available.
                    fifo_file.write(self.frame.tobytes())
                except IOError:
                    continue

    def set_frame_data(self, frame):
        """ Method updates the image data. This currently encodes the
            numpy array to jpg but can be modified to support other encodings.
            frame - Numpy array containing the image data of the next frame
                    in the project stream.
        """
        ret, jpeg = cv2.imencode('.jpg', cv2.resize(frame, self.resolution))
        if not ret:
            raise Exception('Failed to set frame data')
        self.frame = jpeg

    def join(self):
        self.stop_request.set()

def lambda_handler(event, context):
    """Empty entry point to the Lambda function invoked from the edge."""
    return

def infinite_infer_run():
    """ Run the DeepLens inference loop frame by frame"""

    # Create a local display instance that will dump the image bytes to a FIFO
    # file that the image can be rendered locally.
    local_display = LocalDisplay('480p')
    local_display.start()

    # Load the model here
    projectVersionArn = "arn:aws:rekognition:us-east-2:510335724440:project/PPE_detection_May_2020/version/PPE_detection_May_2020.2020-06-01T23.33.22/1591025603184"

    rekognition = boto3.client('rekognition')   
    customLabels = []

    while True:
        # Get a frame from the video stream
        ret, frame = awscam.getLastFrame()
        # Do inference with the model here
        if (ret != True):
            break
        
        # if (frameId % 6 == 0):
        hasFrame, imageBytes = cv2.imencode(".jpg", frame)

        if(hasFrame):
            response = rekognition.detect_custom_labels(
                Image={
                    'Bytes': imageBytes.tobytes(),
                },
                ProjectVersionArn = projectVersionArn
            )

        image = Image.fromarray(frame)
        imgWidth, imgHeight = image.size  
        draw = ImageDraw.Draw(image)

        for elabel in response["CustomLabels"]:
            elabel["Timestamp"] = (frameId/frameRate)*1000
            customLabels.append(elabel)

            print('Label ' + str(elabel['Name'])) 
            print('Confidence ' + str(elabel['Confidence'])) 
            if 'Geometry' in elabel:
                box = elabel['Geometry']['BoundingBox']
                left = imgWidth * box['Left']
                top = imgHeight * box['Top']
                width = imgWidth * box['Width']
                height = imgHeight * box['Height']
            
                # fnt = ImageFont.truetype('Arial.ttf', 15)
                # if str(elabel['Name']) == 'person':
                #     draw.text((left,top), elabel['Name'], fill='#00d400', font=fnt) 
                # else:
                #     draw.text((left,top), elabel['Name'], fill='#800000', font=fnt)

                # cv2.putText(image, text, org, font, fontScale, color[, thickness[, lineType[, bottomLeftOrigin]]])
                # cv2.putText(imgcv,label,(x1,y1),cv2.FONT_HERSHEY_COMPLEX,0.5,(0,0,0),1)
                if str(elabel['Name']) == 'person':
                    cv2.putText(image, elabel['Name'], (left,top), cv2.FONT_HERSHEY_COMPLEX, 0.5, (0,255,0)，1) 
                else:
                    cv2.putText(image, elabel['Name'], (left,top), cv2.FONT_HERSHEY_COMPLEX, 0.5, (255,0,0)，1)

                
                print('Left: ' + '{0:.0f}'.format(left))
                print('Top: ' + '{0:.0f}'.format(top))
                print('Label Width: ' + "{0:.0f}".format(width))
                print('Label Height: ' + "{0:.0f}".format(height))

                # points = (
                #     (left,top),
                #     (left + width, top),
                #     (left + width, top + height),
                #     (left , top + height),
                #     (left, top))
                # if str(elabel['Name']) == 'person':
                #     draw.line(points, fill='#00d400', width=3)
                # else:
                #     draw.line(points, fill='#800000', width=3)
                
                # cv2.rectangle(image, start_point, end_point, color, thickness)              
                if str(elabel['Name']) == 'person':
                    cv2.rectangle(image, (left,top), (left + width, top + height), (0, 255, 0), 2)
                else:
                    cv2.rectangle(image, (left,top), (left + width, top + height), (255, 0, 0), 2)

        local_display.set_frame_data(frame)

        # alternatively save them all the s3 bucket
        # image.save("frameID: " + format(frameId) + ".jpg") 
        
        # Send results back to IoT or output to video stream
infinite_infer_run()