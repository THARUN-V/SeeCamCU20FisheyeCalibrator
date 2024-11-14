import argparse

class Params:
    
    def __init__(self):
        
        self.parser = argparse.ArgumentParser(description="Fisheye Calibrator for SeeCamCU20 USB Camera")
        
        self.parser.add_argument("--chessboard_w",type=int,default=6,help="No of corners in horizontal direction in chessboard. (default = 7)")
        self.parser.add_argument("--chessboard_h",type=int,default=4,help="No of corners in vertical direction in chessboard. (default = 7)")
        self.parser.add_argument("--chessboard_sqr_size",type=float,default=0.04,help="size of black square in chessborad (in m). (default = 0.04)")
        self.parser.add_argument("--resolution",type=int,default=0,help="resolution of camers. (default : 0 : (640,480)), available resolution 0:(640,480) , 1:(960,540) , 2:(1280,720) , 3:(1280,960) , 4:(1920,1080)")
        
        
        #################### resolution of camera ############################
        self.cam_resolution = {
            0 : (640,480),
            1 : (960,540),
            2 : (1280,720),
            3 : (1280,960),
            4 : (1920,1080)
        }
        
        self.args = self.parser.parse_args()
        
        self.img_w , self.img_h = self.cam_resolution[self.args.resolution]