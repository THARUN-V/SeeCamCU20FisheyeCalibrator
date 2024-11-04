import pyudev
import os
from prettytable import PrettyTable
from collections import defaultdict
import sys

class SeeCam:
    def __init__(self,ser_num,cam_index):
        self.serial_number = ser_num
        self.camera_index = cam_index

class CamContext:
    
    def __init__(self):
        
        self.context = pyudev.Context()
        self.cam_model = "See3CAM_CU20"
        
        self.connected_cams = None
                    
    def get_seecam(self):
        """
        function to get the seecam serial number and the /dev/video associated with it.
        """
        
        # This will hold serial numbers as keys and lists of device nodes as values
        seecam_video_devices = defaultdict(list)
        
        # Iterate over all devices in the video4linux subsystem
        for device in self.context.list_devices(subsystem = "video4linux"):
            if device.get("ID_MODEL","Unknown") == self.cam_model:
               device_node = device.device_node
               serial_number = device.get("ID_SERIAL_SHORT","Unknown")
               
               # Append the device node to the list for the corresponding serial number
               seecam_video_devices[serial_number].append(device_node)
               
        seecam_video_devices = {serial_num:dev[0] for serial_num , dev in dict(seecam_video_devices).items()}
        
        if len(seecam_video_devices) != 0:
            # construct seecam object for easy accesing of serial number and camera index using this object
            self.connected_cams = [SeeCam(key,val) for key,val in seecam_video_devices.items()]
            return self.connected_cams
        else:
            return None
        
    def print_seecam(self):
        table = PrettyTable()
        table.field_names=["CamId","CamDev"]
        
        if self.connected_cams == None:
            print("========= No Cameras Connected ==========")
            sys.exit()
        else:   
            for cam in self.connected_cams:
                table.add_row([cam.serial_number,cam.camera_index])
            
        print(table)