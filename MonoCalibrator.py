from Calibrator import *
from calib_logger import CalibLogger

import pickle
import random
from io import BytesIO
import time

class MonoCalibrator(Calibrator):
    """
    Calibration class for monocular cameras:
        images = [cv2.imread("mono%d.png") for i in range(8)]
        mc = MonoCalibrator()
        mc.cal(images)
        print(mc.as_message())
    """
    is_mono = True
    
    def __init__(self,*args,**kwargs):
        super(MonoCalibrator,self).__init__(*args,**kwargs)
        self.logger = CalibLogger().get_logger()
        
        
    def cal(self,images):
        """
        Calibrate camera from given images
        """
        goodcorners = self.collect_corners(images)
        self.cal_fromcorners(goodcorners)
        self.calibrated = True
        
    def collect_corners(self,images):
        """
        :param images: source images containing chessboards
        :type images: list of : class : "cvMat"
        
        Find chessboards in all images.
        
        Return [(corners,ChessboardInfo)]
        """
        
        self.size = (images[0].shape[1],images[0].shape[0])
        corners = [self.get_corners(i) for i in images]
        
        goodcorners = [(co,b) for (ok,co,b) in corners if ok]
        if not goodcorners:
            raise CalibrationException("No corners found in images!")
        return goodcorners
    
    def cal_fromcorners(self,good):
        """
        :param good: Good corner positions and boards
        :type good: [(corners,ChessboardInfo)]
        """
        (ipts,boards) = zip(*good)
        opts = self.mk_object_points(boards)
        
        # If FIX_ASPECT_RATIO flag is set, enforce focal lengths have 1/1 ratio
        intrinsics_in = numpy.eye(3,dtype = numpy.float64)
        
        if self.camera_model == CAMERA_MODEL.PINHOLE:
            # print("mono pinhole calibration ..")
            self.logger.info("######### Mono Pinhole Calibration #########")
            reproj_err , self.intrinsics , dist_coeffs , rvecs , tvecs = cv2.calibrateCamera(
                opts,
                ipts,
                self.size,
                intrinsics_in,
                None,
                flags = self.calib_flags
            )
            # OpenCV returns more than 8 coefficients (the additional ones all zeros) when CALIB_RATIONAL_MODEL is set.
            # The extra ones include e.g. thin prism coefficients, which we are not interested in.
            if self.calib_flags & cv2.CALIB_RATIONAL_MODEL:
                self.distortion = dist_coeffs.flat[:8].reshape(-1,1) # rational polynomial
            else:
                self.distortion = dist_coeffs.flat[:5].reshape(-1,1) # plumb bob
        elif self.camera_model == CAMERA_MODEL.FISHEYE:
            self.logger.info("######### Mono Fisheye Calibration #########")
            # WARNING : cv2.fisheye.calibrate wants float64 points
            ipts64 = numpy.asarray(ipts,dtype = numpy.float64)
            ipts = ipts64
            opts64 = numpy.asarray(opts,dtype = numpy.float64)
            opts = opts64
            reproj_err , self.intrinsics , self.distortion , rvecs , tvecs = cv2.fisheye.calibrate(
                opts,
                ipts,
                self.size,
                intrinsics_in,
                None,
                flags = self.fisheye_calib_flags
            )
            
        # R is identity matrix for monocular calibration
        self.R = numpy.eye(3,dtype = numpy.float64)
        self.P = numpy.zeros((3,4),dtype = numpy.float64)
        
        self.set_alpha(0.0)
        
    def set_alpha(self,a):
        """
        Set the alpha value for the calibrated camera solution. The alpha value is a zoom, and ranges from 0
        (zoomed in, all pixels in calibrated image are valid) to 1 (zoomed out, all pixels in original image are in calibrated image).
        """
        
        if self.camera_model == CAMERA_MODEL.PINHOLE:
            # NOTE : Prior to Electric, this code was broken such that we never actually saved the new
            # camera matrix. In effect, this enforced P = [K|0] for monocular cameras.
            # TODO : Verify that OpenCV #1199 gets applied (imporved GetOptimalNewCameraMatrix)
            ncm , _ = cv2.getOptimalNewCameraMatrix(self.intrinsics,self.distortion,self.size,a)
            for j in range(3):
                for i in range(3):
                    self.P[j,i] = ncm[j,i]
            self.mapx , self.mapy = cv2.initUndistortRectifyMap(self.intrinsics,self.distortion,self.R,ncm,self.size,cv2.CV_32FC1)
        elif self.camera_model == CAMERA_MODEL.FISHEYE:
            # NOTE : cv2.fisheye.estimateNewCameraMatrixForUndistortRectify not producing proper results, using a naive approach instead:
            self.P[:3,:3] = self.intrinsics[:3,:3]
            self.P[0,0] = (1. + a)
            self.P[1,1] = (1. + a)
            self.mapx , self.mapy  = cv2.fisheye.initUndistortRectifyMap(self.intrinsics,self.distortion,self.R,self.P,self.size,cv2.CV_32FC1)
            
    def remap(self,src):
        """
        :param src: source image
        :type src: :class:"cvMat"
        
        Apply the post-calibration undistortion to the source iamge
        """
        return cv2.remap(src,self.mapx,self.mapy,cv2.INTER_LINEAR)
    
    def undistort_points(self,src):
        """
        :param src: N souce pixel points (u,v) as an Nx2 matrix
        :type src: :class:"cvMat"
        
        Apply the post-calibration undistortion to the source points
        """
        if self.camera_model == CAMERA_MODEL.PINHOLE:
            return cv2.undistortPoints(src,self.intrinsics,self.distortion,R = self.R , P = self.P)
        elif self.camera_model == CAMERA_MODEL.FISHEYE:
            return cv2.fisheye.undistortPoints(src,self.intrinsics,self.distortion,R = self.R , P = self.P)
        
    def report(self):
        self.lrreport(self.distortion,self.intrinsics,self.R,self.P)
        
    def ost(self):
        return self.lrost(self.distortion,self.intrinsics,self.R,self.P,self.size)
    
    def yaml(self):
        return self.lryaml(self.distortion,self.intrinsics,self.R,self.P,self.size,self.camera_model)
    
    def linear_error_from_image(self,image):
        """
        Detect the checkerboard and compute the linear error.
        Mainly for use in tests.
        """
        _ ,corners,_,board,_ = self.downsample_and_detect(image)
        
        if corners is None:
            return None 
        
        undistorted = self.undistort_points(corners)
        return self.linear_error(undistorted,board)
    
    @staticmethod
    def linear_error(corners,b):
        """
        Returns the linear error for a set of corners detected in the unrectified image.
        """
        
        if corners is None:
            return None 
        
        corners = numpy.squeeze(corners)
        
        def pt2line(x0,y0,x1,y1,x2,y2):
            """
            point is (x0,y0) , line is (x1,y1,x2,y2)
            """
            return abs((x2-x1) * (y1-y0) - (x1-x0) * (y2-y1)) / math.sqrt((x2-x1) ** 2 + (y2-y1) **2)
        
        n_cols = b.n_cols
        n_rows = b.n_rows
        
        n_pts = n_cols * n_rows
        
        ids = numpy.arange(n_pts).reshape((n_pts,1))
        
        ids_to_idx = dict((ids[i,0],i) for i in range(len(ids)))
        
        errors = []
        for row in range(n_rows):
            row_min = row * n_cols
            row_max = (row+1) * n_cols
            pts_in_row = [x for x in ids if row_min <= x < row_max]
            
            # not enough points to calculate error
            if len(pts_in_row) <= 2 : continue
            
            left_pt = min(pts_in_row)[0]
            right_pt = max(pts_in_row)[0]
            x_left = corners[ids_to_idx[left_pt],0]
            y_left = corners[ids_to_idx[left_pt],1]
            x_right = corners[ids_to_idx[right_pt],0]
            y_right = corners[ids_to_idx[right_pt],1]
            
            for pt in pts_in_row:
                if pt[0] in (left_pt,right_pt) : continue
                x = corners[ids_to_idx[pt[0]],0]
                y = corners[ids_to_idx[pt[0]],1]
                errors.append(pt2line(x,y,x_left,y_left,x_right,y_right))
                
        if errors:
            return math.sqrt(sum([e**2 for e in errors])/len(errors))
        else:
            return None
            
    def handle_msg(self,msg):
        """
        Detects the calibration target and, if found and provides enough new information, adds it to the sample database.
        
        Returns a MonoDrawable message with the display image and progress info.
        """
        
        gray = self.mkgray(msg)
        linear_error = -1
        
        # Get display-image-to-be (scrib) and detection of the calibration target.
        scrib_mono , corners , downsampled_corners , board , (x_scale,y_scale) = self.downsample_and_detect(gray)
        
        if self.calibrated:
            # Show rectified image
            gray_remap = self.remap(gray)
            gray_rect = gray_remap
            if x_scale != 1.0 or y_scale != 1.0:
                gray_rect = cv2.resize(gray_remap,(scrib_mono.shape[1],scrib_mono.shape[0]))
                
            scrib = cv2.cvtColor(gray_rect,cv2.COLOR_GRAY2BGR)
            
            if corners is not None:
                # Report linear error
                undistorted = self.undistort_points(corners)
                linear_error = self.linear_error(undistorted,board)
                
                # Draw rectified corners
                scrib_src = undistorted.copy()
                scrib_src[:,:,0] /= x_scale
                scrib_src[:,:,1] /= y_scale
                cv2.drawChessboardCorners(scrib,(board.n_cols,board.n_rows),scrib_src,True)
                
        else:
            scrib = cv2.cvtColor(scrib_mono,cv2.COLOR_GRAY2BGR)
            if corners is not None:
                # Draw (potentially downsampled) corners onto display image
                cv2.drawChessboardCorners(scrib,(board.n_cols,board.n_rows),downsampled_corners,True)
            
                # Add sample to database only if it's sufficiently different from any previous sample.
                params = self.get_parameters(corners,board,(gray.shape[1],gray.shape[0]))
                if self.is_good_sample(params,corners,self.last_frame_corners):
                    self.db.append((params,gray))
                    self.good_corners.append((corners,board))
                    self.logger.info("### Added sample %d , p_x = %.3f , p_y = %.3f , p_size = %.3f , skew = %.3f ###"%tuple([len(self.db)]+params))
                
        self.last_frame_corners = corners
        
        rv = MonoDrawable()
        rv.scrib = scrib 
        rv.params = self.compute_goodenough()
        rv.linear_error = linear_error
        
        return rv
    
    def do_calibration(self,dump = False):
        if not self.good_corners:
            self.logger.info("******** Collecting corners for all images! ************")
            images = [i for (p,i) in self.db]
            self.good_corners = self.collect_corners(images)
        self.size = (self.db[0][1].shape[1],self.db[0][1].shape[0])
        # Dump should only occur if user wants it
        if dump:
            pickle.dump((self.is_mono,self.size,self.good_corners),
                        open("/tmp/camera_calibration_%08x.pickle"%random.getrandbits(32),"w"))
        self.cal_fromcorners(self.good_corners)
        self.calibrated = True
        # DEBUG
        print((self.report()))
        print((self.ost()))
        
    def do_tarfile_save(self,tf):
        """
        write images and calibration solution to a tarfile object.
        """
        
        def taradd(name,buf):
            if isinstance(buf,str):
                s = BytesIO(buf.encode("utf-8"))
            else:
                s = BytesIO(buf)
                
            ti = tarfile.Tarinfo(name)
            ti.size = len(s.getvalue())
            ti.uname = "calibrator"
            ti.mtime = int(time.time())
            tf.addfile(tarinfo = ti,fileobj = s)
            
        ims = [("left-%04d.png" % i , im) for i,(_,im) in enumerate(self.db)]
        
        for (name,im) in ims:
            taradd(name,cv2.imencode(".png",im)[1].tostring())
        taradd("ost.yaml",self.yaml())
        taradd("ost.txt",self.ost())
        
    def do_tarfile_calibration(self,filename):
        archive = tarfile.open(filename,"r")
        
        images = [image_from_archive(archive,f) for f in archive.getname() if (f.startswith("left") and (f.endswith(".pgm") or f.endswith("png")))]
        
        self.cal(images)