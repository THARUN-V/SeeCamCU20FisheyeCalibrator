import argparse

class Params:
    
    def __init__(self):
        
        self.parser = argparse.ArgumentParser(description="Fisheye Calibrator for SeeCamCU20 USB Camera")
        
        self.parser.add_argument("--chessboard_w",type=int,default=6,help="No of corners in horizontal direction in chessboard. (default = 7)")
        self.parser.add_argument("--chessboard_h",type=int,default=4,help="No of corners in vertical direction in chessboard. (default = 7)")
        self.parser.add_argument("--chessboard_sqr_size",type=float,default=0.04,help="size of black square in chessborad (in m). (default = 0.04)")
        
        #################### resolution of camera ############################
        
        
        self.args = self.parser.parse_args()