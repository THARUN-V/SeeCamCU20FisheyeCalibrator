import logging

class CalibLogger:
    
    _instance = None # Singleton instance variable
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CalibLogger,cls).__new__(cls)
            
            # Initialize logger
            cls._instance.logger = logging.getLogger("CalibLogger")
            cls._instance.logger.setLevel(logging.DEBUG)
            
            # console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            
            # Define logging format
            formatter = logging.Formatter("[%(asctime)s,%(levelname)s]%(message)s",datefmt='%Y-%m-%d %H:%M:%S')
            console_handler.setFormatter(formatter)
            
            # Add the console handler to the logger
            cls._instance.logger.addHandler(console_handler)
            
        return cls._instance
    
    def get_logger(self):
        return self.logger