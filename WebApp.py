from CamContext import *
from flask import Flask , render_template , request

class WebApp(CamContext):
    
    def __init__(self):
        self.app = Flask(__name__)
        self.setup_routes()
        
        ##### get the cameras connected #####
        CamContext.__init__(self)
        self.cams = self.get_seecam()
        self.print_seecam()
        
    def setup_routes(self):
        
        @self.app.route("/",methods = ["GET","POST"])
        def home():
            cam_table = list()
            if request.method == "POST":
                for cam in self.cams:
                    cam_table.append({"serial_number":cam.serial_number,"video_device":cam.camera_index})
            return render_template("index.html",data=cam_table)
        
    def run(self):
        self.app.run(debug=True,use_reloader=False)