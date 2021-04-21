
class Logger:
    VERBOSITY = 0

    def __init__(self, v):
        self.VERBOSITY = v

    def log(self, msg):
        if(self.VERBOSITY):
            print(msg)
