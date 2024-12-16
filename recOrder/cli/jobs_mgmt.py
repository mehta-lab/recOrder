import submitit, os, json, time
import socket
from pathlib import Path
from tempfile import TemporaryDirectory

# Jobs query object
# Todo: Not sure where these should functions should reside - ask Talon

# def modify_dict(shared_var_jobs, k, v, lock):
#     with lock:
#         for key in shared_var_jobs.keys():
#             print(key)
#             tmp = shared_var_jobs[key]
#             tmp["count"] += 1
#             shared_var_jobs[key] = tmp
#         shared_var_jobs[k] = {"count":0, "val": v}
#         print(shared_var_jobs)

SERVER_PORT = 8089

class JobsManagement():
    
    def __init__(self, *args, **kwargs):
        # self.m = Manager()
        # self.shared_var_jobs = self.m.dict()        
        # self.lock = self.m.Lock()
        self.shared_var_jobs = dict()        
        self.executor = submitit.AutoExecutor(folder="logs")
        self.logsPath = self.executor.folder
        self.tmp_path = TemporaryDirectory()
        self.tempDir = os.path.join(Path(self.tmp_path.name), "tempfiles")

    def checkForJobIDFile(self, jobID, extension="out"):
        files = os.listdir(self.logsPath)
        try:
            for file in files:
                if file.endswith(extension):
                    if jobID in file:
                        file_path = os.path.join(self.logsPath, file)
                        f = open(file_path, "r")
                        txt = f.read()                    
                        f.close()
                        return txt
        except Exception as exc:
            print(exc.args)
        return ""

    def startClient(self):
        try:
            self.clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.clientsocket.settimeout(300)
            self.clientsocket.connect(('localhost', SERVER_PORT))
            self.clientsocket.settimeout(None)
        except Exception as exc:
            print(exc.args)

    def stopClient(self):
        try:
            self.clientsocket.close()
        except Exception as exc:
            print(exc.args)

    def putJobInListClient(self, uid: str, job: str):
        try:
            json_obj = {uid:job}
            json_str = json.dumps(json_obj)
            self.clientsocket.send(bytes(json_str, 'UTF-8'))
            # p1 = Process(target=modify_dict, args=(self.shared_var_jobs, uid, job, self.lock))
            # p1.start()    
            # p1.join()
            # p2 = Process(target=increment, args=(self.shared_var_jobs, self.lock))
            # p2.start()    
            # p2.join()
        except Exception as exc:
            print(exc.args)

    def hasSubmittedJob(self, uuid_str: str)->bool:
        if uuid_str in self.shared_var_jobs.keys():
            return True
        return False
    
    ####### below - not being used #########

    def getJobs(self):
        return self.shared_var_jobs

    def getJob(self, uuid_str: str)->submitit.Job:
        if uuid_str in self.shared_var_jobs.keys():
            return self.shared_var_jobs[uuid_str]
            
    def cancelJob(self, uuid_str: str):
        if uuid_str in self.shared_var_jobs.keys():
            job: submitit.Job = self.shared_var_jobs[uuid_str]
            job.cancel()

    def getInfoOnJob(self, uuid_str: str)->list:
        if uuid_str in self.shared_var_jobs.keys():
            job: submitit.Job = self.shared_var_jobs[uuid_str]
            return job.results()    
