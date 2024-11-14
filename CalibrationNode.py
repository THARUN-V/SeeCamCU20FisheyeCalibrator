from utils import *
from MonoCalibrator import *
from calib_logger import CalibLogger

import os


class CalibrationNode():
    def __init__(self,
                 boards,
                 flags = 0,
                 fisheye_flags = 0,
                 checkerboard_flags = 0,
                 max_chessboard_speed = -1,
                 queue_size = 1,
                 cam_index = None,
                 img_w = 640,
                 img_h = 480):
        
        self._boards = boards
        self._calib_flags = flags 
        self._fisheye_calib_flags = fisheye_flags
        self._checkerboard_flags = checkerboard_flags
        self._max_chessboard_speed = max_chessboard_speed
        self._cam_index = cam_index
        self._img_w = img_w
        self._img_h = img_h
        
        self.q_mono = BufferQueue(queue_size)
        
        self.c = None 
        self.cap = None
        
        self._last_display = None
        
        cam_cap_th = threading.Thread(target = self.queue_monocular)
        cam_cap_th.daemon = True
        cam_cap_th.start()
        
        mth = ConsumerThread(self.q_mono,self.handle_monocular)
        mth.daemon = True
        mth.start()
        
    def redraw_monocular(self,*args):
        pass
    
    # need to modify this function to fetch image from camer capture class
    def queue_monocular(self):
        self.cap = cv2.VideoCapture(self._cam_index)
        # self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
        # self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,self._img_w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT,self._img_h)
        
        while self.cap.isOpened():
            ret,frame = self.cap.read()
            if ret:
                self.q_mono.put(frame)
        
        # self.q_mono.put(msg)
    
    def release(self):
        self.cap.release()
        
    def handle_monocular(self,msg):
        if self.c == None:
            self.c = MonoCalibrator(self._boards,
                                    self._calib_flags,
                                    self._fisheye_calib_flags,
                                    self._checkerboard_flags,
                                    self._max_chessboard_speed)
        # This should just call the MonoCalibrator
        drawable = self.c.handle_msg(msg)
        self.displaywidth = drawable.scrib.shape[1]
        self.redraw_monocular(drawable)
        
        
class OpenCVCalibrationNode(CalibrationNode):
    """
    Calibration node with an OpenCV Gui.
    """
    FONT_FACE = cv2.FONT_HERSHEY_SIMPLEX
    FONT_SCALE = 0.6
    FONT_THICKNESS = 2
    
    def __init__(self,*args,**kwargs):
        
        CalibrationNode.__init__(self,*args,**kwargs)
        
        self.queue_display = BufferQueue(maxsize = 1)
        # self.initWindow()
        self.image = None
        
        self.CALIBRATE_BUTTON_X_MIN = 693
        self.CALIBRATE_BUTTON_X_MAX = 799
        self.CALIBRATE_BUTTON_Y_MIN = 305
        self.CALIBRATE_BUTTON_Y_MAX = 411
        
        self.logger = CalibLogger().get_logger()
        
    def spin(self):
        
        while True:
            if self.queue_display.qsize() > 0:
                self.image = self.queue_display.get()
                # cv2.imshow("display",self.image)
            else:
                time.sleep(0.1)
            k = cv2.waitKey(6) & 0xFF
            if k in [27,ord("q")]:
                pass 
            elif k == ord("s") and self.image is not None:
                self.screendump(self.image)                        
                
    def initWindow(self):
        cv2.namedWindow("display",cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("display",self.on_mouse)
        cv2.createTrackbar("CameraType : \n 0 : pinhole \n 1 : fisheye","display",0,1,self.on_model_change)
        cv2.createTrackbar("scale","display",0,100,self.on_scale)
        
    @classmethod
    def putText(cls,img,text,org,color = (0,0,0)):
        cv2.putText(img,text,org,cls.FONT_FACE,cls.FONT_SCALE,color,thickness = cls.FONT_THICKNESS)
        
    @classmethod
    def getTextSize(cls,text):
        return cv2.getTextSize(text,cls.FONT_FACE,cls.FONT_SCALE,cls.FONT_THICKNESS)[0]
    
    
    def on_mouse(self,x,y):
        if self.CALIBRATE_BUTTON_X_MIN <= x <= self.CALIBRATE_BUTTON_X_MAX and self.CALIBRATE_BUTTON_Y_MIN <= y <= self.CALIBRATE_BUTTON_Y_MAX:
            if self.c.goodenough:
                # print("***** Calibrating ********")
                self.logger.info("########## CALIBRATING ##########")
                self.c.do_calibration()
                self.buttons(self._last_display)
                self.queue_display.put(self._last_display)
    
    # def on_mouse(self,event,x,y,flags,param):
    #     if event == cv2.EVENT_LBUTTONDOWN and self.displaywidth < x:
    #         if self.c.goodenough:
    #             if 180 <= y < 280:
    #                 print("***** Calibrating ********")
    #                 self.c.do_calibration()
    #                 self.buttons(self._last_display)
    #                 self.queue_display.put(self._last_display)
    #         if self.c.calibrated:
    #             if 280 <= y < 300:
    #                 self.c.do_save()
    #             elif 380 <= y < 400:
    #                 pass
                
    def on_model_change(self,model_select_val):
        if self.c == None:
            print("Cannot change camera model until the first image has been receives")
            return
        
        self.c.set_cammodel(CAMERA_MODEL.PINHOLE if model_select_val < 0.5 else CAMERA_MODEL.FISHEYE)
        
    def on_model_change(self,model_select_val):
        self.c.set_cammodel(CAMERA_MODEL.PINHOLE if model_select_val < 0.5 else CAMERA_MODEL.FISHEYE)
        
    def on_scale(self,scalevalue):
        if self.c.calibrated:
            self.c.set_alpha(scalevalue/100.0)
            
    def button(self,dst,label,enable):
        dst.fill(255)
        size = (dst.shape[1],dst.shape[0])
        if enable:
            color = (155,155,80)
        else:
            color = (224,224,224)
        cv2.circle(dst,(size[0]//2,size[1]//2),min(size)//2,color,-1)
        (w,h) = self.getTextSize(label)
        self.putText(dst,label,((size[0]-w)//2,(size[1]+h)//2),(255,255,255))

    def buttons(self,display):
        x = self.displaywidth
        
        # self.button(display[180:280,x:x+100],"CALIBRATE",self.c.goodenough)
        # self.button(display[280:380,x:x+100],"SAVE",self.c.calibrated)
        # self.button(display[380:480,x:x+100],"COMMIT",self.c.calibrated)
        
        self.button(display[280:380,x:x+100],"CALIBRATE",self.c.goodenough)
        self.button(display[380:480,x:x+100],"NEXT",self.c.calibrated)
        
    def y(self,i):
        """
        Set up right-size images
        """        
        return 30 + 40 * i 
    
    def screendump(self,im):
        i = 0
        while os.access("/tmp/dump%d.png"% i , os.R_OK):
            i += 1 
        cv2.imwrite("/tmp/dump%d.png"% i , im)
        print("Saved screen dump to /tmp/dump%d.png"%i)
        
    def redraw_monocular(self,drawable):
        height = drawable.scrib.shape[0]
        width = drawable.scrib.shape[1]
        
        display = numpy.zeros((max(480,height),width+100,3),dtype = numpy.uint8)
        display[0:height , 0:width , :] = drawable.scrib
        display[0:height , width:width+100 , :].fill(255)
        
        self.buttons(display)
        if not self.c.calibrated:
            if drawable.params:
                for i , (label,lo,hi,progress) in enumerate(drawable.params):
                    (w,_) = self.getTextSize(label)
                    self.putText(display,label,(width+(100-w)//2,self.y(i)))
                    color = (0,255,0)
                    if progress < 1.0:
                        color = (0,int(progress*255),255)
                    cv2.line(display,(int(width+lo*100),self.y(i)+20),(int(width+hi*100),self.y(i)+20),color,4)
        
        else:
            self.putText(display,"lin.",(width,self.y(0)))
            linerror = drawable.linear_error
            if linerror is None or linerror < 0:
                msg = "?"
            else:
                msg = "%.2f" % linerror 
            self.putText(display,msg,(width,self.y(1)))
            
        self._last_display = display
        self.queue_display.put(display)