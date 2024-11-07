from CamContext import *
from flask import Flask , render_template , request , jsonify , url_for
import json
import re

class WebApp(CamContext):
    
    def __init__(self):
        self.app = Flask(__name__)
        self.setup_routes()
        
        # initialize seecam class #
        CamContext.__init__(self)
        
        # json path
        self.json_path = "CameraStartUpJson.json"
        
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
            
            return [{"CameraName":cam_details[0],"SerialNumber":cam_details[1].split(" ")[0]} for cam_details in DeviceIdWithCamName]
            
            
    def setup_routes(self):
        
        @self.app.route("/",methods = ["GET","POST"])
        def home():
            cam_table = list()
            if request.method == "POST":
                
                # self.update_cam_property()
                
                # for cam in self.get_seecam():
                #     cam_table.append({"serial_number":cam.serial_number,"video_device":cam.camera_index})
                cam_table = self.update_cam_details()
            return render_template("index.html",data=cam_table)
        
        @self.app.route('/process',methods = ['POST'])
        def process():
            # Get the SerialNumber fromt the request
            serial_number = request.json.get("SerialNumber")
            if serial_number is None:
                return "<p>Error : No Serial Number provided. </p>", 400
            
            # Find the specific row data based on SerialNumber
            # row_data = next((row for row in data if row["SerialNumber"] == serial_number),None)
            # if not row_data:
            #     return "<p> Error : Serial Number not found. </p>", 400
            
            # Simulate processing and generate new HTML content
            # Replace this with actual processing logic as needed.
            # processed_message = f"Processing complete for {row_data['CameraName']} with Serial Number {row_data['SerialNumber']}."
            processed_message = f"Processing complete for {serial_number}."

            # Return the processed result as HTML content
            return f"""
            <h1>Process Result</h1>
            <p>{processed_message}</p>
            <a href="{url_for('home')}">Go Back</a>
            """
        
    def run(self):
        self.app.run(debug=True,use_reloader=False)