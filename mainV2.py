from flask import Flask, render_template, redirect, url_for, Response , request , jsonify
import json
import re
import numpy as np
import cv2

from CamContext import *
from CalibrationNode import *


class SeeCamCalibrationNode:
    
    def __init__(self):
        self.node = None
        
    def initialize_calibration_node(self, cam_index):
        if self.node is None:
            boards = [ChessboardInfo(6, 4, 0.04)]
            calib_flags = 0
            fisheye_calib_flags = 0
            checkerboard_flags = cv2.CALIB_CB_FAST_CHECK
            
            self.node = OpenCVCalibrationNode(boards,
                                              calib_flags,
                                              fisheye_calib_flags,
                                              checkerboard_flags=checkerboard_flags,
                                              max_chessboard_speed=-1.0,
                                              queue_size=1,
                                              cam_index=cam_index)
            
    def generate_frames(self):
        if self.node is not None:
            while True:
                if self.node.queue_display.qsize() > 0:
                    frame = self.node.queue_display.get()
                    ret, buffer = cv2.imencode('.jpg', frame)
                    if not ret:
                        continue
                    frame = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

class WebApp(CamContext):
    
    def __init__(self):
        self.app = Flask(__name__)
        self.setup_routes()
        
        CamContext.__init__(self)
        
        self.see_cam_serial_num_and_idx = {cam.serial_number: cam.camera_index for cam in self.get_seecam()}
        
        # json path
        self.json_path = "CameraStartUpJson.json"
        
        # variable to keep track and update table
        self.data = self.update_cam_details()
        
        self.calib_node = SeeCamCalibrationNode()
        
    def update_cam_details(self):
        try:
            with open(self.json_path, "r") as f:
                camera_startup_json = json.load(f)

            CamParams = camera_startup_json["CamParams"][0]
            CamIdsDict = {val: key for key, val in CamParams.items() if key in ["frontCameraId", "rightCameraId", "leftCameraId"]}
            
            # using this, update the camera id's with respect to their camera name
            CamIdsMappedToJson = {re.findall(r'[A-Z][a-z]*|[a-z]+', CamIdsDict[cam.serial_number])[0].title(): cam.serial_number for cam in self.get_seecam()}
            
            # return this as a list of dictionary to print it in webpage
            return [{"CameraName": cam_name, "SerialNumber": serial_number} for cam_name, serial_number in CamIdsMappedToJson.items()]
            
        except FileNotFoundError:
            # If file is not found, we simulate loading default data
            CamSerialNumAndDeviceId = [f"{cam.serial_number} {cam.camera_index}" for cam in self.get_seecam()]
            SortedDeviceId = sorted(CamSerialNumAndDeviceId, key=lambda x: int(x.split(" ")[-1].split("video")[-1]))
            
            DeviceIdWithCamName = list(zip(["Front", "Right", "Left"], SortedDeviceId))
            
            return [{"CameraName": cam_details[0], "SerialNumber": cam_details[1].split(" ")[0], "processed": False} for cam_details in DeviceIdWithCamName]

    def setup_routes(self):
        @self.app.route("/", methods=["GET"])
        def home():
            return render_template("start_page_v2.html")  # Render start page with button
        
        @self.app.route("/table", methods=["GET"])
        def table():
            return render_template("table_v2.html", data=self.data)  # Render table with camera data

        @self.app.route("/start_calibration/<serial_number>", methods=["GET"])
        def start_calibration(serial_number):
            # Start calibration logic
            print(f"Calibration started for camera with serial number: {serial_number}")
            self.calib_node.initialize_calibration_node(self.see_cam_serial_num_and_idx[serial_number])
            # After starting calibration, redirect to video feed page
            return redirect(url_for('video_feed', serial_number=serial_number))

        @self.app.route("/video_feed/<serial_number>", methods=["GET"])
        def video_feed(serial_number):
            # Stream the video using the generate_frames method
            return Response(self.calib_node.generate_frames(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')
            
        @self.app.route("/process_click", methods=["POST"])
        def process_click():
            data = request.get_json()
            serial_number = data["serialNumber"]
            x, y = data["x"], data["y"]
            print(f"Mouse Clicked At x : {x} , y : {y}")
            # Predefined target area where the click will be considered as a valid calibration point
            target_x_min = 50
            target_x_max = 150
            target_y_min = 50
            target_y_max = 150

            if target_x_min <= x <= target_x_max and target_y_min <= y <= target_y_max:
                # If the click is within the target area, mark the camera as calibrated
                for row in self.data:
                    if row["SerialNumber"] == serial_number:
                        row["processed"] = True  # Mark as processed
                        break
                return jsonify({"message": "Calibration successful"}), 200
            else:
                return jsonify({"message": "Click outside target area"}), 400

    def run(self):
        self.app.run(debug=True, use_reloader=False)


if __name__ == "__main__":
    app = WebApp()
    app.run()