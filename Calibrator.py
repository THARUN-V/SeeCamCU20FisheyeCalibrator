from utils import *
import tarfile
from params import Params

class Calibrator():
    """
    Base class for calibration system
    """
    def __init__(self,
                 boards,
                 flags = 0,
                 fisheye_flags = 0,
                 checkerboard_flags = cv2.CALIB_CB_FAST_CHECK,
                 max_chessboard_speed = -1.0):
        
        self.params = Params()

        # Make sure n_cols > n_rows to agree with OpenCV CB detector outupt
        self._boards = [ChessboardInfo(max(i.n_cols,i.n_rows),min(i.n_cols,i.n_rows),i.dim) for i in boards]
        
        # Set to true after we perform calibration
        self.calibrated = False
        self.calib_flags = flags
        self.fisheye_calib_flags = fisheye_flags
        self.checkerboard_flags = checkerboard_flags
        
        self.camera_model = CAMERA_MODEL.PINHOLE
        
        # self.db is list of (parameters,image) samples for use in calibration.
        # parameters has form (X,Y,size,skew) all normalized to [0,1], to keep track of what sort of samples we've taken and ensure enough variety
        self.db = []
        # for each db sample, we also record the detected corners.
        self.good_corners = []
        # Set to true when we have sufficiently varied samples to calibrate
        self.goodenough = False
        self.param_ranges = [0.7,0.7,0.4,0.5]
        self.last_frame_corners = None
        self.max_chessboard_speed = max_chessboard_speed
        
    def mkgray(self,img):
        """
        Convert RGB image to GrayScale image
        """
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    def get_parameters(self,corners,board,size):
        """
        Return list of parameters [X,Y,size,skew] describing the checkerboard view.
        """
        (width,height) = size
        Xs = corners[:,:,0]
        Ys = corners[:,:,1]
        
        outside_corners = get_outside_corners(corners,board)
        
        area = calculate_area(outside_corners)
        skew = calculate_skew(outside_corners)
        border = math.sqrt(area)
        
        # For X and Y, we "shrink" the image all around by approx. half the board size.
        # Otherwise large boards are penalized because you can't get much X/Y variation.
        p_x = min(1.0,max(0.0,(numpy.mean(Xs)-border/2)/(width-border)))
        p_y = min(1.0,max(0.0,(numpy.mean(Ys)-border/2)/(height-border)))
        p_size = math.sqrt(area/(width*height))
        
        params = [p_x,p_y,p_size,skew]
        
        return params
    
    def set_cammodel(self,modeltype):
        self.camera_model = modeltype
        
    def is_slow_moving(self,corners,last_frame_corners):
        """
        Returns true if the motion of the checkerboard is sufficiently low between this and the previous frame.
        """
        # If we don't have previous frame corners, we can't accept the sample
        if last_frame_corners is None:
            return False
        num_corners = len(corners)
        corners_deltas = (corners - last_frame_corners).reshape(num_corners,2)
        
        # Average distance travelled overall for all corners
        average_motion = numpy.average(numpy.linalg.norm(corners_deltas,axis = 1))
        return average_motion <= self.max_chessboard_speed
    
    def is_good_sample(self,params,corners,last_frame_corners):
        """
        Returns true if the checkerboard detection described by params should be added to the database.
        """
        if not self.db:
            return True
        
        def param_distance(p1,p2):
            return sum([abs(a-b) for (a,b) in zip(p1,p2)])
        
        db_params = [sample[0] for sample in self.db]
        d = min([param_distance(params,p) for p in db_params])
        
        # TODO what's a good threshold here ? should it be configurable?
        
        if d <= 0.2:
            return False 
        
        if self.max_chessboard_speed > 0:
            if not self.is_slow_moving(corners,last_frame_corners):
                return False 
            
        # All tests passed , image should be good for calibration
        return True

    _param_names = ["x","Y","Size","Skew"]
    
    def compute_goodenough(self):
        if not self.db:
            return None 
        
        # Find range of checkerboard poses covered by samples in database
        all_params = [sample[0] for sample in self.db]
        min_params = all_params[0]
        max_params = all_params[0]
        for params in all_params[1:]:
            min_params = lmin(min_params,params)
            max_params = lmax(max_params,params)
            
        # Don't reward small size or skew
        min_params = [min_params[0],min_params[1],0.,0.]
        
        # For each parameter, judge how much progress has been made toward adequate variation.
        progress = [min((hi - lo)/r,1.0) for (lo,hi,r) in zip(min_params,max_params,self.param_ranges)]
        # If we have lots of samples, allow calibration even if not all parameters are given
        # self.goodenough = (len(self.db) >= 40) or all([p == 1.0 for p in progress])
        self.goodenough = (len(self.db) >= self.params.args.sample_count) or all([p == 1.0 for p in progress])
        
        return list(zip(self._param_names,min_params,max_params,progress))
    
    def mk_object_points(self,boards,use_board_size = False):
        opts = []
        for i,b in enumerate(boards):
            num_pts = b.n_cols * b.n_rows
            opts_loc = numpy.zeros((num_pts,1,3),numpy.float32)
            for j in range(num_pts):
                opts_loc[j,0,0] = (j // b.n_cols)
                opts_loc[j,0,1] = (j % b.n_cols)
                opts_loc[j,0,2] = 0
                if use_board_size:
                    opts_loc[j,0,:] = opts_loc[j,0,:] * b.dim
            opts.append(opts_loc)
        return opts
    
    def get_corners(self,img,refine = True):
        """
        Use cvFindChessboardCorners to find corners of chessboard in image.
        
        check all boards. Return corners for first chessboard that it detects if given multiple size chessboards.
        
        Returns (ok,corners,board)
        """
        
        for b in self._boards:
            (ok,corners) = get_corners(img,b,refine,self.checkerboard_flags)
            
            if ok:
                return (ok,corners,b)
        return (False,None,None)
    
    def downsample_and_detect(self,img):
        """
        Downsample the input image to approximately VGA resolution and detect the
        calibration target corners in the full-size image.
        
        Combines these apparently orthogonal duties as an optimization. Checkerboard
        detection is too expensive on large iamges, so it's better to do detection on
        the smaller display image and scale the corners back up to the correct size.
        
        Returns (scrib,corners,downsampled_corners,board,(x_scale,y_scale))
        """
        height = img.shape[0]
        width = img.shape[1]
        scale = math.sqrt((width*height)/(640.*480.))
        
        if scale > 1.0:
            scrib = cv2.resize(img,(int(width/scale),int(height/scale)))
        else:
            scrib = img 
            
        # Due to rounding, actual horizontal/vertical scaling may differ slightly
        x_scale = float(width) / scrib.shape[1]
        y_scale = float(height) / scrib.shape[0]
        
        # Detect checkerboard
        (ok,downsampled_corners,board) = self.get_corners(scrib,refine = True)
        
        # scale corners back to full size image
        corners = None 
        if ok:
            if scale > 1.0:
                # Refine up-scaled corners in the original full-res image
                corners_unrefined = downsampled_corners.copy()
                corners_unrefined[:,:,0] *= x_scale
                corners_unrefined[:,:,1] *= y_scale
                radius = int(math.ceil(scale))
                if len(img.shape) == 3 and img.shape[2] == 3:
                    mono = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
                else:
                    mono = img 
                cv2.cornerSubPix(mono,corners_unrefined,(radius,radius),(-1,-1),(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,30,0.1))
                
                corners = corners_unrefined
            else:
                corners = downsampled_corners
        
        return (scrib,corners,downsampled_corners,board,(x_scale,y_scale))
    
    @staticmethod
    def lrreport(d,k,r,p):
        print("D = ",numpy.ravel(d).tolist())
        print("K = ",numpy.ravel(k).tolist())
        print("R = ",numpy.ravel(r).tolist())
        print("P = ",numpy.ravel(p).tolist())
        
    @staticmethod
    def lrost(d,k,r,p,size):
        assert k.shape == (3,3)
        assert r.shape == (3,3)
        assert p.shape == (3,4)
        
        calmessage = "\n".join([
            "# OST version 5.0 parameters",
            "",
            "",
            "[image]",
            "widht",
            "%d"%size[0],
            "",
            "height",
            "%d" %size[1],
            "",
            "camera matrix",
            "".join("%8f"%k[0,i] for i in range(3)),
            "".join("%8f"%k[1,i] for i in range(3)),
            "".join("%8f"%k[2,i] for i in range(3)),
            "",
            "rectification",
            "".join("%8f"%r[0,i] for i in range(3)),
            "".join("%8f"%r[1,i] for i in range(3)),
            "".join("%8f"%r[2,i] for i in range(3)),
            "",
            "projection",
            "".join("%8f"%p[0,i] for i in range(4)),
            "".join("%8f"%p[1,i] for i in range(4)),
            "".join("%8f"%p[2,i] for i in range(4)),
            ""
        ])
        # assert len(calmessage) < 255 , "Calibration info must be less than 525 bytes"
        return calmessage
    
    @staticmethod
    def lryaml(d,k,r,p,size,cam_model):
        def format_mat(x,precision):
            return ("[%s]" %(
                numpy.array2string(x,precision = precision , suppress_small = True , seperator = ", ").replace("[","").replace("]","").replace("\n","\n          ")
            ))
            
        dist_model = get_dist_model(d,cam_model)
        
        assert k.shape == (3,3)
        assert r.shape == (3,3)
        assert p.shape == (3,4)
        
        calmessage = "\n".join([
            "image_width : %d"%size[0],
            "image_height : %d"%size[1],
            "camera_matrix : ",
            " rows : 3",
            " cols : 3",
            " data : "+format_mat(k,5),
            "distortion_model : ",dist_model,
            "distortion_coefficients : ",
            " rows : 1",
            " cols : %d" %d.size,
            " data : [%s]" % ", ".join("%8f" % x for x in d.flat),
            "recification_matrix : ",
            " rows : 3",
            " cols : 3",
            " data "+ format_mat(r,8),
            "projection_matrix : ",
            " rows : 3",
            " cols : 4",
            " data : " + format_mat(p,5),
            ""
        ])
        return calmessage
    
    def do_save(self):
        filename = "/tmp/calibration.tar.gz"
        tf = tarfile.open(filename,"w:gz")
        self.do_tarfile_save(tf) # Must be overridden in subclass
        tf.close()
        print("Wrote calibration data to",filename)