#! /usr/bin/python3

import os
import time
import tarfile
import subprocess
import datetime

from pathlib import Path

class Settings:
    collectorVersion = "3.0.5-develop"
    osVersion = "Ubuntu20_04LTS"

    platformLocation = "/opt/solo/bin/platform"
    jsonrpcLocation = "/opt/solo/bin/solo-jsonrpc"
    librariesLocation = "/opt/solo/lib/"

    testFolder = os.getcwd() + "/test"
    folderToMound = "//collector-build.initi/build_repo/Develop/"

    pathToArchive = "/3.0.5-develop/Ubuntu20_04LTS/2022-09-20_104645/collector_llvm_2022-09-20_104645.tgz"


class RemoteFolder:
    localFolderPrefix = "remote."

    def __init__(self, remoteFolder, localFolder):
        timeStamp = datetime.datetime.now().timestamp()
        self.remoteFolder    = Path(remoteFolder)
        self.initialLocation = Path(os.getcwd())
        self.localFolder     = Path(f"{self.initialLocation}/{self.localFolderPrefix}{timeStamp}")
        self.errCode = 0

    def __enter__(self):
        self.localFolder.mkdir()
        self.errCode = self._mount(self.remoteFolder, self.localFolder)
        if (self.errCode == 0):
            return self.localFolder
        else:
            return None

    def __exit__(self, exc_type, exc_value, traceback):
        if (self.localFolder.exists()):
            self.errCode = self._umount(self.localFolder)
            if (self.errCode == 0):
                os.rmdir(self.localFolder)

    def _mount(self, remoteFolder, localFolder):
        return subprocess.call(["mount", "-t", "cifs", "-o", "username=nobody,password=nopass", remoteFolder, localFolder])

    def _umount(self, localFolder):
        return subprocess.call(["umount", "-f", localFolder])




def main():
    with RemoteFolder(Settings.folderToMound, Settings.testFolder) as localFolder:
        print(localFolder)
        with tarfile.open(f"{localFolder}{Settings.pathToArchive}", 'r') as archive:
            archiveMembers = archive.getmembers()
            print(archiveMembers)


if __name__ == '__main__':
    print("************************\n")
    main()
    print("\n************************")
