from CamContext import *
from flask import Flask

class WebApp(CamContext):
    
    def __init__(self):
        self.app = Flask(__name__)
        self.setup_routes()
        
        ##### get the cameras connected #####
        CamContext.__init__(self)
        self.cams = self.get_seecam()
        self.print_seecam()
        
    def setup_routes(self):
        
        @self.app.route("/")
        def home():
            return "Hello, World"
        
    def run(self):
        self.app.run(debug=True,use_reloader=False)