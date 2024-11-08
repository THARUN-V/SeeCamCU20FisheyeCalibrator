from CamContext import *
from flask import Flask , render_template , request , jsonify , url_for , Response
import json
import re

from CalibrationNode import *


class SeeCamCalibrationNode:
    
    def __init__(self):
        self.node = None
        
    def initialize_calibration_node(self,cam_index):
        if self.node is None:
            boards = [ChessboardInfo(6,4,0.04)]
            calib_flags = 0
            fisheye_calib_flags = 0
            checkerboard_flags = cv2.CALIB_CB_FAST_CHECK
            
            self.node = OpenCVCalibrationNode(boards,
                                        calib_flags,
                                        fisheye_calib_flags,
                                        checkerboard_flags = checkerboard_flags,
                                        max_chessboard_speed = -1.0,
                                        queue_size = 1,
                                        cam_index = cam_index)
            
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
        
        # initialize seecam class #
        CamContext.__init__(self)
        
        # json path
        self.json_path = "CameraStartUpJson.json"
        
        # variable to keep track and update table
        self.data = self.update_cam_details()
        
        self.calib_node = SeeCamCalibrationNode()
        
    def update_cam_details(self):
        """
        opens camera startup json, check which camera id belongs to front,right and left.
        """
        
        ### open camera startup json ###
        try:
            with open(self.json_path,"r") as f:
                camera_startup_json = json.load(f)

            CamParams = camera_startup_json["CamParams"][0]
            CamIdsDict = {val:key for key,val in CamParams.items() if key in ["frontCameraId","rightCameraId","leftCameraId"]}
            
            # using this, update the camera id's with respect to their camera name
            CamIdsMappedToJson = {re.findall(r'[A-Z][a-z]*|[a-z]+',CamIdsDict[cam.serial_number])[0].title():cam.serial_number for cam in self.get_seecam()}
            
            # return this as a list of dictionary to print it in webpage
            return [{"CameraName":cam_name ,"SerialNumber":serial_number}for cam_name , serial_number in CamIdsMappedToJson.items()]
            
        except FileNotFoundError:
            
            # CamNameDefault = {0:"Front",1:"Right",2:"Left"}
            
            CamSerialNumAndDeviceId = [f"{cam.serial_number} {cam.camera_index}" for cam in self.get_seecam()]
            SortedDeviceId = sorted(CamSerialNumAndDeviceId,key= lambda x:int(x.split(" ")[-1].split("video")[-1]))
            
            DeviceIdWithCamName = list(zip(["Front","Right","Left"],SortedDeviceId))
            
            return [{"CameraName":cam_details[0],"SerialNumber":cam_details[1].split(" ")[0],"processed":False} for cam_details in DeviceIdWithCamName]
            
            
    def setup_routes(self):
        
        @self.app.route("/",methods = ["GET","POST"])
        def home():
            if request.method == "POST":
                return render_template("index.html",data=self.data)
            else:
                return render_template("index.html")
        
        @self.app.route('/process',methods = ['POST'])
        def process():
            try:
                # Get the data from the request body
                request_data = request.get_json()
                serial_number = request_data.get("SerialNumber")
                
                # Find the row in the data list
                row_data = next((row for row in self.data if row["SerialNumber"] == serial_number),None)
                
                if row_data:
                    # # simulate processing here (e.g perform calibration)
                    # row_data["processed"] = True
                    # # Return a success response to the frontend
                    # return jsonify({"message":"Processing completed successfullty"}),200
                    
                    see_cam = {cam.serial_number : cam.camera_index for cam in self.get_seecam()}
                    
                    self.calib_node.initialize_calibration_node(see_cam[row_data["SerialNumber"]])
                    
                    row_data["processed"] = True
                    # Return a success response to the frontend
                    return jsonify({"message":"Processing completed successfullty"}),200
                    
                else:
                    return jsonify({"message":"Serial Number not found."}),404
            except Exception as e:
                # In case of an error, return an error message
                return jsonify({"message":f"Error during processing : {str(e)}"}) , 500
            
    
        @self.app.route("/video_feed")
        def video_feed():
            return Response(self.calib_node.generate_frames(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')
            
        
    def run(self):
        self.app.run(debug=True,use_reloader=False)