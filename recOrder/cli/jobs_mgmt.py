import os, json, shutil
import socket
import submitit
import threading, time

DIR_PATH = os.path.dirname(os.path.realpath(__file__))
FILE_PATH = os.path.join(DIR_PATH, "main.py")

SERVER_PORT = 8089 # Choose an available port
JOBS_TIMEOUT = 5 # 5 mins
SERVER_uIDsjobIDs = {} # uIDsjobIDs[uid][jid] = job
class JobsManagement():
    
    def __init__(self, *args, **kwargs):
        self.executor = submitit.AutoExecutor(folder="logs")
        self.logsPath = self.executor.folder
        self.clientsocket = None
        self.uIDsjobIDs = {} # uIDsjobIDs[uid][jid] = job        
        
    def clearLogs(self):        
        thread = threading.Thread(target=self.clearLogFiles, args={self.logsPath,})
        thread.start()

    def clearLogFiles(self, dirPath, silent=True):
        for filename in os.listdir(dirPath):
            file_path = os.path.join(dirPath, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                if not silent:
                    print('Failed to delete %s. Reason: %s' % (file_path, e))

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
    
    def setShorterTimeout(self):
        self.clientsocket.settimeout(3)

    def startClient(self):
        try:
            self.clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.clientsocket.settimeout(300)
            self.clientsocket.connect(('localhost', SERVER_PORT))
            self.clientsocket.settimeout(None)

            thread = threading.Thread(target=self.stopClient)
            thread.start()
        except Exception as exc:
            print(exc.args)

    def stopClient(self):
        try:
            time.sleep(2)
            while True:
                time.sleep(1)
                buf = ""
                try:
                    buf = self.clientsocket.recv(1024)
                except:
                    pass
                if len(buf) > 0:
                    if b"\n" in buf:
                        dataList = buf.split(b"\n")
                        for data in dataList:
                            if len(data)>0:
                                decoded_string = data.decode()
                                json_str = str(decoded_string)
                                json_obj = json.loads(json_str)
                                u_idx = json_obj["uID"]
                                job_idx = str(json_obj["jID"])
                                cmd = json_obj["command"]
                                if cmd == "clientRelease":
                                    if self.hasSubmittedJob(u_idx, job_idx):
                                        self.clientsocket.close()
                                        break
                                if cmd == "cancel":
                                    if self.hasSubmittedJob(u_idx, job_idx):
                                        try:
                                            job = self.uIDsjobIDs[u_idx][job_idx]
                                            job.cancel()
                                        except Exception as exc:
                                            pass # possibility of throwing an exception based on diff. OS
                forDeletions = []
                for uID in self.uIDsjobIDs.keys():
                    for jID in self.uIDsjobIDs[uID].keys():
                        job = self.uIDsjobIDs[uID][jID]
                        if job.done():
                            forDeletions.append((uID, jID))
                for idx in range(len(forDeletions)):
                    del self.uIDsjobIDs[forDeletions[idx][0]][forDeletions[idx][1]]
                forDeletions = []
                for uID in self.uIDsjobIDs.keys():
                    if len(self.uIDsjobIDs[uID].keys()) == 0:                        
                        forDeletions.append(uID)
                for idx in range(len(forDeletions)):
                    del self.uIDsjobIDs[forDeletions[idx]]
                if len(self.uIDsjobIDs.keys()) == 0:
                    self.clientsocket.close()
                    break
        except Exception as exc:
            self.clientsocket.close()
            print(exc.args)

    def checkAllExpJobsCompletion(self, uID):
        if uID in self.uIDsjobIDs.keys():
            for jobEntry in self.uIDsjobIDs[uID]:
                jobsBool = jobEntry["jID"]
                if jobsBool == False:
                    return False
        return True

    def putJobCompletionInList(self, jobBool, uID: str, jID: str, mode="client"):
        if uID in self.uIDsjobIDs.keys():
            if jID in self.uIDsjobIDs[uID].keys():
                self.uIDsjobIDs[uID][jID] = jobBool

    def putJobInList(self, job, uID: str, jID: str, well:str, mode="client"):
        try:
            well = str(well)
            if ".zarr" in well:
                wells = well.split(".zarr")
                well = wells[1].replace("\\","-").replace("/","-")[1:]
            if mode == "client":
                if uID not in self.uIDsjobIDs.keys():
                    self.uIDsjobIDs[uID] = {}
                    self.uIDsjobIDs[uID][jID] = job
                else:
                    if jID not in self.uIDsjobIDs[uID].keys():
                        self.uIDsjobIDs[uID][jID] = job
                json_obj = {uID:{"jID": str(jID), "pos": well}}
                json_str = json.dumps(json_obj)+"\n"
                self.clientsocket.send(json_str.encode())
            else:
                # from server side jobs object entry is a None object
                # this will be later checked as completion boolean for a ExpID which might
                # have several Jobs associated with it
                if uID not in SERVER_uIDsjobIDs.keys():
                    SERVER_uIDsjobIDs[uID] = {}
                    SERVER_uIDsjobIDs[uID][jID] = job
                else:
                    if jID not in SERVER_uIDsjobIDs[uID].keys():
                        SERVER_uIDsjobIDs[uID][jID] = job
        except Exception as exc:
            print(exc.args)

    def hasSubmittedJob(self, uID: str, mode="client")->bool:
        if mode == "client":
            if uID in self.uIDsjobIDs.keys():
                return True
            return False
        else:
            if uID in SERVER_uIDsjobIDs.keys():
                return True
            return False
    
    def hasSubmittedJob(self, uID: str, jID: str, mode="client")->bool:
        if mode == "client":
            if uID in self.uIDsjobIDs.keys():
                if jID in self.uIDsjobIDs[uID].keys():
                    return True
            return False
        else:
            if uID in SERVER_uIDsjobIDs.keys():
                if jID in SERVER_uIDsjobIDs[uID].keys():
                    return True
            return False
