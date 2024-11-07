from enum import Enum
import math
import numpy
import cv2
from queue import Queue
import threading

# Supported camera models
class CAMERA_MODEL(Enum):
    PINHOLE = 0
    FISHEYE = 1
    
class CalibrationException(Exception):
    pass

def lmin(seq1,seq2):
    """
    Pairwise minimum of two sequences.
    """
    return [min(a,b) for (a,b) in zip(seq1,seq2)]

def lmax(seq1,seq2):
    """
    Pairwise maximum of two sequences.
    """
    return [max(a,b) for (a,b) in zip(seq1,seq2)]

def pdist(p1,p2):
    """
    Distance between two points. p1 = (x,y) , p2 = (x,y)
    """
    return math.sqrt(math.pow(p1[0]-p2[0],2) + math.pow(p1[1] - p2[1],2))

def get_outside_corners(corners,board):
    """
    Return the four corners of the board as a whole, as (up_left,up_right,down_right,down_left)
    """
    xdim = board.n_cols
    ydim = board.n_rows
    
    if corners.shape[1] * corners.shape[0] != xdim * ydim:
        raise Exception("Invalid number of corners! %d corners. X : %d , Y : %d"%(corners.shape[1] * corners.shape[0],xdim,ydim))
    
    up_left = corners[0,0]
    up_right = corners[xdim-1,0]
    down_right = corners[-1,0]
    down_left = corners[-xdim,0]
    
    return (up_left,up_right,down_right,down_left)
    
def calculate_area(corners):
    """
    Get 2d image area of the detected checkerboard
    The projected checkerboard is assumed to be a convex quadrilateral, and the area computed as |p X Q| / 2
    """
    (up_left, up_right, down_right, down_left) = corners
    a = up_right - up_left
    b = down_right - up_right
    c = down_left - down_right
    p = b + c 
    q = a + b
    
    return abs(p[0]*q[1] - p[1]*q[0]) / 2.

def calculate_skew(corners):
    """
    Get skew for given checkerboard detection.
    Scaled to [0,1], which 0 = no skew , 1 = high skew
    Skew is proportional to the divergence of three outside corners from 90 degrees.
    """
    up_left , up_right , down_right , _ = corners
    
    def angle(a,b,c):
        """
        Return angle between lines ab , bc
        """
        ab = a - b
        cb = c - b
        return math.acos(numpy.dot(ab,cb) / (numpy.linalg.norm(ab) * numpy.linalg.norm(cb)))
    
    skew = min(1.0,2. * abs((math.pi / 2.) - angle(up_left , up_right , down_right)))
    return skew

def get_corners(img,board,refine = True , checkerboard_flags = 0):
    """
    Get corners for a particular chessboard for an image.
    """
    h = img.shape[0]
    w = img.shape[1]
    if len(img.shape) == 3 and img.shape[2] == 3:
        mono = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    else:
        mono = img 
    (ok,corners) = cv2.findChessboardCorners(mono , (board.n_cols,board.n_rows) , flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE | checkerboard_flags)
    
    if not ok:
        return (ok,corners)
    
    # If any corners are withing BORDER pixels of the screen edge, reject the detection by setting ok to false
    # NOTE : This may cause problem with very low-resolution cameras, where 8 pixels is a non-negligible fraction
    # of the image size.
    BORDER = 8
    if not all([(BORDER < corners[i,0,0] < (w - BORDER)) and (BORDER < corners[i,0,1] < (h - BORDER)) for i in range(corners.shape[0])]):
        ok = False 
    
    # Ensure that all corner-arrays are going from top to bottom
    if board.n_rows != board.n_cols:
        if corners[0,0,1] > corners[-1,0,1]:
            corners = numpy.copy(numpy.flipud(corners))
    else:
        direction_corners = (corners[-1]-corners[0]) >= numpy.array([[0.0,0.0]])
        
        if not numpy.all(direction_corners):
            if not numpy.any(direction_corners):
                corners = numpy.copy(numpy.flipud(corners))
            elif direction_corners[0][0]:
                corners = numpy.rot90(corners.reshape(board.n_rows,board.n_cols,2)).reshape(board.n_cols*board.n_rows,1,2)
            else:
                corners = numpy.rot90(corners.reshape(board.n_rows,board.n_cols,2),3).reshape(board.n_cols*board.n_rows,1,2)
                
    if refine and ok:
        # Use a radius of half the minimum distance between corners. This should be large enough to snap to the 
        # correct corner, but not so large as to include a wrong corner in the search window.
        min_distance = float("inf")
        for row in range(board.n_rows):
            for col in range(board.n_cols-1):
                index = row * board.n_rows + col 
                min_distance = min(min_distance , _pdist(corners[index,0],corners[index+1,0]))
        for row in range(board.n_rows-1):
            for col in range(board.n_cols):
                index = row*board.n_rows + col 
                min_distance = min(min_distance,_pdist(corners[index,0],corners[index+board.n_cols,0]))
        radius = int(math.ceil(math.ceil(min_distance * 0.5)))
        cv2.cornerSubPix(mono,corners,(radius,radius),(-1,-1),(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,30,0.1))
        
    return (ok,corners)

def get_dist_model(dist_params,cam_model):
    # select dist model
    if CAMERA_MODEL.PINHOLE == cam_model:
        if dist_params.size > 5:
            dist_model = "rational_polynomial"
        else:
            dist_model = "plumb_bob"
    elif CAMERA_MODEL.FISHEYE == cam_model:
        dist_model = "equidistant"
    else:
        dist_model = "unknown"
    return dist_model

class ChessboardInfo():
    
    def __init__(self,
                 n_cols = 0,
                 n_rows = 0,
                 dim = 0.0):
        self.n_cols = n_cols
        self.n_rows = n_rows
        self.dim = dim
        
def image_from_archive(archive,name):
    """
    Load image PGM file from tar archive
    Used for tarfile loading and unit test.
    """
    member = archive.getmember(name)
    imagefiledata = numpy.frombuffer(archive.extractfile(member).read(),numpy.uint8)
    imagefiledata.resize((1,imagefiledata.size))
    return cv2.imdecode(imagefiledata,cv2.IMREAD_COLOR)

class ImageDrawable():
    """
    Passed to CalibrationNode after image handled. Allows plotting of images
    with detected corner points
    """
    def __init__(self):
        self.params = None 
        
class MonoDrawable(ImageDrawable):
    def __init__(self):
        ImageDrawable.__init__(self)
        self.scrib = None 
        self.linear_error = -1.0
        

class BufferQueue(Queue):
    """
    Slight modification of the standard Queue that discards the oldest item 
    when adding and item and the queue is full.
    """
    def put(self,item,*args,**kwargs):
        with self.mutex:
            if self.maxsize > 0 and self._qsize() == self.maxsize:
                self._get()
            self._put(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()
            
class ConsumerThread(threading.Thread):
    def __init__(self,queue,function):
        threading.Thread.__init__(self)
        self.queue = queue
        self.function = function
            
    def run(self):
        while True:
            m = self.queue.get()
            self.function(m)