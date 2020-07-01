# *****************************************************
#                                                    *
# Copyright 2018 Amazon.com, Inc. or its affiliates. *
# All Rights Reserved.                               *
#                                                    *
# *****************************************************
""" A sample lambda for object detection"""
from threading import Thread, Event
import os
import json
import numpy as np
import awscam
import cv2
import greengrasssdk

# extra imports for rekognition
# from threading import Thread, Event, Timer
import mo
import boto3

# import math
import io

# from PIL import Image, ImageDraw, ExifTags, ImageColor, ImageFont


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
        RESOLUTION = {"1080p": (1920, 1080), "720p": (1280, 720), "480p": (858, 480)}
        if resolution not in RESOLUTION:
            raise Exception("Invalid resolution")
        self.resolution = RESOLUTION[resolution]
        # Initialize the default image to be a white canvas. Clients
        # will update the image when ready.
        self.frame = cv2.imencode(".jpg", 255 * np.ones([640, 480, 3]))[1]
        self.stop_request = Event()

    def run(self):
        """ Overridden method that continually dumps images to the desired
            FIFO file.
        """
        # Path to the FIFO file. The lambda only has permissions to the tmp
        # directory. Pointing to a FIFO file in another directory
        # will cause the lambda to crash.
        result_path = "/tmp/results.mjpeg"
        # Create the FIFO file if it doesn't exist.
        if not os.path.exists(result_path):
            os.mkfifo(result_path)
        # This call will block until a consumer is available
        with open(result_path, "w") as fifo_file:
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
        ret, jpeg = cv2.imencode(".jpg", cv2.resize(frame, self.resolution))
        if not ret:
            raise Exception("Failed to set frame data")
        self.frame = jpeg

    def join(self):
        self.stop_request.set()


def infinite_infer_run():
    """ Entry point of the lambda function"""
    try:
        # This object detection model is implemented as single shot detector (ssd), since
        # the number of labels is small we create a dictionary that will help us convert
        # the machine labels to human readable labels.
        model_type = "ssd"
        output_map = {
            1: "aeroplane",
            2: "bicycle",
            3: "bird",
            4: "boat",
            5: "bottle",
            6: "bus",
            7: "car",
            8: "cat",
            9: "chair",
            10: "cow",
            11: "dinning table",
            12: "dog",
            13: "horse",
            14: "motorbike",
            15: "person",
            16: "pottedplant",
            17: "sheep",
            18: "sofa",
            19: "train",
            20: "tvmonitor",
        }
        # Create an IoT client for sending to messages to the cloud.
        client = greengrasssdk.client("iot-data")
        iot_topic = "$aws/things/{}/infer".format(os.environ["AWS_IOT_THING_NAME"])
        # Create a local display instance that will dump the image bytes to a FIFO
        # file that the image can be rendered locally.
        local_display = LocalDisplay("480p")
        local_display.start()
        # The sample projects come with optimized artifacts, hence only the artifact
        # path is required.
        model_path = (
            "/opt/awscam/artifacts/mxnet_deploy_ssd_resnet50_300_FP16_FUSED.xml"
        )
        # Load the model onto the GPU.
        client.publish(topic=iot_topic, payload="Loading object detection model")
        model = awscam.Model(model_path, {"GPU": 1})
        client.publish(topic=iot_topic, payload="Object detection model loaded")
        # Set the threshold for detection
        detection_threshold = 0.25
        # The height and width of the training set images
        input_height = 300
        input_width = 300

        """extra part of code for rekognition"""

        # model trained in us east 2
        # projectVersionArn = "arn:aws:rekognition:us-east-2:510335724440:project/PPE_detection_May_2020/version/PPE_detection_May_2020.2020-06-01T23.33.22/1591025603184"
        # model trained in us east 1, version 1
        # projectVersionArn = "arn:aws:rekognition:us-east-1:510335724440:project/ppe-detection-deeplens/version/ppe-detection-deeplens.2020-06-12T14.25.57/1591943158364"
        # model trained in us east 1, version 2
        projectVersionArn = "arn:aws:rekognition:us-east-1:510335724440:project/ppe-detection-deeplens/version/ppe-detection-deeplens.2020-06-17T14.28.47/1592375328862"

        rekognition = boto3.client("rekognition")
        customLabels = []

        s3 = boto3.client("s3")

        iterator = 0
        """extra part of code for rekognition"""
        # Do inference until the lambda is killed.
        while True:
            # Get a frame from the video stream
            ret, frame = awscam.getLastFrame()
            if not ret:
                raise Exception("Failed to get frame from the stream")
            # Resize frame to the same size as the training set.
            frame_resize = cv2.resize(frame, (input_height, input_width))
            # Run the images through the inference engine and parse the results using
            # the parser API, note it is possible to get the output of doInference
            # and do the parsing manually, but since it is a ssd model,
            # a simple API is provided.
            parsed_inference_results = model.parseResult(
                model_type, model.doInference(frame_resize)
            )
            # Compute the scale in order to draw bounding boxes on the full resolution
            # image.
            yscale = float(frame.shape[0]) / float(input_height)
            xscale = float(frame.shape[1]) / float(input_width)
            # Dictionary to be filled with labels and probabilities for MQTT
            cloud_output = {}
            # Get the detected objects and probabilities
            # for obj in parsed_inference_results[model_type]:
            #     if obj["prob"] > detection_threshold:
            #         # Add bounding boxes to full resolution frame
            #         xmin = int(xscale * obj["xmin"])
            #         ymin = int(yscale * obj["ymin"])
            #         xmax = int(xscale * obj["xmax"])
            #         ymax = int(yscale * obj["ymax"])
            #         # See https://docs.opencv.org/3.4.1/d6/d6e/group__imgproc__draw.html
            #         # for more information about the cv2.rectangle method.
            #         # Method signature: image, point1, point2, color, and tickness.

            #         # comment out the drawing part to avoid the results of two models all on one frame
            #         cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (255, 165, 20), 10)
            #         # Amount to offset the label/probability text above the bounding box.
            #         text_offset = 15
            #         # See https://docs.opencv.org/3.4.1/d6/d6e/group__imgproc__draw.html
            #         # for more information about the cv2.putText method.
            #         # Method signature: image, text, origin, font face, font scale, color,
            #         # and tickness
            #         cv2.putText(
            #             frame,
            #             "{}: {:.2f}%".format(
            #                 output_map[obj["label"]], obj["prob"] * 100
            #             ),
            #             (xmin, ymin - text_offset),
            #             cv2.FONT_HERSHEY_SIMPLEX,
            #             2.5,
            #             (255, 165, 20),
            #             6,
            #         )
            #         # Store label and probability to send to cloud
            #         cloud_output[output_map[obj["label"]]] = obj["prob"]
            # # Set the next frame in the local display stream.
            # local_display.set_frame_data(frame)
            # # Send results to the cloud
            # client.publish(topic=iot_topic, payload=json.dumps(cloud_output))

            """extra part of code for rekognition"""
            hasFrame, imageBytes = cv2.imencode(".jpg", frame)
            client.publish(topic=iot_topic, payload="import done")
            if hasFrame:
                response = rekognition.detect_custom_labels(
                    Image={"Bytes": imageBytes.tobytes(),},
                    ProjectVersionArn=projectVersionArn,
                )
            client.publish(topic=iot_topic, payload="analyse done")                    

            # image = Img.fromarray(frame)
            # imgWidth, imgHeight = image.size
            # draw = ImageDraw.Draw(image)
            imgHeight, imgWidth, c = frame.shape
            image = frame

            ppe = 0
            person = 0

            for elabel in response["CustomLabels"]:
                # elabel["Timestamp"] = (frameId/frameRate)*1000
                customLabels.append(elabel)

                print("Label " + str(elabel["Name"]))
                print("Confidence " + str(elabel["Confidence"]))
                
                if str(elabel["Name"]) == "PPE":
                    ppe = ppe + 1
                else if str(elabel["Name"]) == "person"
                    person = person + 1
                
                if "Geometry" in elabel:
                    box = elabel["Geometry"]["BoundingBox"]
                    left = imgWidth * box["Left"]
                    top = imgHeight * box["Top"]
                    width = imgWidth * box["Width"]
                    height = imgHeight * box["Height"]
                    
                    if str(elabel["Name"]) == "person":
                        cv2.putText(
                            image,
                            elabel["Name"],
                            (int(left), int(top)),
                            cv2.FONT_HERSHEY_COMPLEX,
                            1,
                            (0, 255, 0),
                            1,
                        )
                    else:
                        cv2.putText(
                            image,
                            elabel["Name"],
                            (int(left), int(top)),
                            cv2.FONT_HERSHEY_COMPLEX,
                            1,
                            (255, 0, 0),
                            1,
                        )

                    print("Left: " + "{0:.0f}".format(left))
                    print("Top: " + "{0:.0f}".format(top))
                    print("Label Width: " + "{0:.0f}".format(width))
                    print("Label Height: " + "{0:.0f}".format(height))

                    # points = (
                    #     (left, top),
                    #     (left + width, top),
                    #     (left + width, top + height),
                    #     (left, top + height),
                    #     (left, top),
                    # )
                    # if str(elabel["Name"]) == "person":
                    #     draw.line(points, fill="#00d400", width=3)
                    # else:
                    #     draw.line(points, fill="#800000", width=3)
                    if str(elabel["Name"]) == "person":
                        cv2.rectangle(
                            image,
                            (int(left), int(top)),
                            (int(left + width), int(top + height)),
                            (0, 255, 0),
                            2,
                        )
                    else:
                        cv2.rectangle(
                            image,
                            (int(left), int(top)),
                            (int(left + width), int(top + height)),
                            (255, 0, 0),
                            2,
                        )
            # save the image locally and then upload them into s3
            client.publish(topic=iot_topic, payload="drawing done")
            # cv2.imwrite("frame" + format(iterator) + ".jpg", image)
            # image.save("frame" + format(iterator) + ".jpg")
            # dont save it to the disk anymore
            #client.publish(topic=iot_topic, payload="image saving done")
            iterator = iterator + 1

            # upload as bytes
            # imageBytes = image.tobytes()
            # with io.BytesIO(imageBytes) as f:
            #     s3.upload_fileobj(
            #         f,
            #         "custom-labels-console-us-east-1-5e4c514f5b",
            #         "frameID: " + format(iterator) + ".jpg",
            #     )

            # write the metadata
            # metadata = {"NumberOfPersons": str(person), "NumberOfPPEs": str(ppe)}
            
            # upload as string
            img_str = cv2.imencode('.jpg', image)[1].tostring()
            s3.put_object(
                Bucket="custom-labels-console-us-east-1-5e4c514f5b",
                Key="frameID: " + format(iterator) + ".jpg",
                Body=img_str,
                ACL="public-read",
                Metadata={"NumberOfPersons": str(person), "NumberOfPPEs": str(ppe)}
            )
            client.publish(topic=iot_topic, payload="send to s3 done")

            # to retrieve meatadata in s3
            # $ aws s3api head-object --bucket custom-labels-console-us-east-1-5e4c514f5b --key testImage.jpg

            # print(customLabels)

            """extra part of code for rekognition"""

        # cap.release() not sure if we need to keep this

    except Exception as ex:
        client.publish(
            topic=iot_topic, payload="Error in object detection lambda: {}".format(ex)
        )


infinite_infer_run()
