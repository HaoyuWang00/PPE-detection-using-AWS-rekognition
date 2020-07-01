# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# PDX-License-Identifier: MIT-0 (For details, see https://github.com/awsdocs/amazon-rekognition-developer-guide/blob/master/LICENSE-SAMPLECODE.)

import json
import boto3
import os
import numpy as np

# from cv2 import cv2
import cv2
import math
import io

# from PIL import Image, ImageDraw, ExifTags, ImageColor, ImageFont
import time
import greengrasssdk


def analyzeVideo():
    videoFile = (
        "Users\WangHaoyu\Desktop\aws-projects\deeplens_inference_function\testVideo.mp4"
    )
    # projectVersionArn = "arn:aws:rekognition:us-east-2:510335724440:project/PPE_detection_May_2020/version/PPE_detection_May_2020.2020-05-17T23.10.52/1589728257151"
    # projectVersionArn = "arn:aws:rekognition:us-east-2:510335724440:project/PPE_detection_May_2020/version/PPE_detection_May_2020.2020-06-01T23.33.22/1591025603184" # best model so far
    # projectVersionArn = "arn:aws:rekognition:us-east-1:510335724440:project/ppe-detection-deeplens/version/ppe-detection-deeplens.2020-06-12T14.25.57/1591943158364"  test model, us east 1
    projectVersionArn = "arn:aws:rekognition:us-east-1:510335724440:project/ppe-detection-deeplens/version/ppe-detection-deeplens.2020-06-17T14.28.47/1592375328862"  # best model in us east 1

    rekognition = boto3.client("rekognition")
    customLabels = []
    0, cv2.CAP_V4L
    cap = cv2.VideoCapture(videoFile)
    frameRate = cap.get(5)  # frame rate
    iterator = 0
    s3 = boto3.client("s3")
    while cap.isOpened():
        frameId = cap.get(1)  # current frame number
        print("Processing frame id: {}".format(frameId))
        ret, frame = cap.read()
        if ret != True:
            break
        if frameId % math.floor(frameRate) == 0:
            # if frameId % 6 == 0:
            hasFrame, imageBytes = cv2.imencode(".jpg", frame)

            if hasFrame:
                response = rekognition.detect_custom_labels(
                    Image={"Bytes": imageBytes.tobytes(),},
                    ProjectVersionArn=projectVersionArn,
                )

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
                else:
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

            iterator = iterator + 1

            # upload as string
            # img_str = cv2.imencode(".jpg", image)[1].tostring()
            img = cv2.imencode(".jpg", image)
            img_str = img[1].tostring()
            s3.put_object(
                Bucket="custom-labels-console-us-east-1-5e4c514f5b",
                Key="frameID" + format(iterator) + ".jpg",
                Body=img_str,
                ACL="public-read",
                Metadata={"NumberOfPersons": str(person), "NumberOfPPEs": str(ppe)},
            )

            # to retrieve meatadata in s3
            # $ aws s3api head-object --bucket custom-labels-console-us-east-1-5e4c514f5b --key testImage.jpg

            # print(customLabels)

        # return len(response['CustomLabels'])

        # time.sleep(10)

    # print(customLabels)

    with open(videoFile + ".json", "w") as f:
        f.write(json.dumps(customLabels))

    cap.release()


analyzeVideo()
