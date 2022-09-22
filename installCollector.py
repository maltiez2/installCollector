#! /usr/bin/python3

import os
import re
import time
import shutil
import tarfile
import datetime
import subprocess

from pathlib import Path
from dataclasses import dataclass


@dataclass
class FileEntry:
    pattern: str           # what to look for
    finalPath: str         # where to put it
    renameTo: str = ""     # what to rename to
    symLinkPath: str = ""  # what to link it to


class Settings:
    collectorVersion = "3.0.5-develop"
    osVersion = "Ubuntu20_04LTS"
    llvm = True

    platformLocation = "/opt/solo/bin/platform"
    jsonrpcLocation = "/opt/solo/bin/solo-jsonrpc"
    librariesLocation = "/opt/solo/lib/"
    changeOwnerToCurrentUser = True
    changeOwnerTo = ""

    testFolder = os.getcwd() + "/test"
    folderToMound = "//collector-build.initi/build_repo/Develop/"

    pathToArchive = "/3.0.5-develop/Ubuntu20_04LTS/2022-09-20_104645/collector_llvm_2022-09-20_104645.tgz"

    files = [
        FileEntry(r"solo-platform-0\.1\.0", "../test/")
        #FileEntry(r"solo-jsonrpc-0\.1\.0",  "/opt/solo/bin/solo-jsonrpc"),
        #FileEntry(r"lib[\w\.\-]*$",         "/opt/solo/lib/")
    ]


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
        if self.errCode == 0:
            return self.localFolder
        else:
            return None

    def __exit__(self, exc_type, exc_value, traceback):
        if self.localFolder.exists():
            self.errCode = self._umount(self.localFolder)
            if self.errCode == 0:
                os.rmdir(self.localFolder)

    def _mount(self, remoteFolder, localFolder):
        return subprocess.call(["mount", "-t", "cifs", "-o", "username=nobody,password=nopass", remoteFolder, localFolder])

    def _umount(self, localFolder):
        return subprocess.call(["umount", "-f", localFolder])


def extract(settings, archive):
    archiveMembers = archive.getmembers()

    for fileEntry in settings.files:
        regex = re.compile(f"\\./{fileEntry.pattern}")
        for member in archiveMembers:
            if not member.isdir() and regex.match(member.name):
                print(f"Extracting '{member.name}' to '{fileEntry.finalPath}'")
                archive.extract(member, fileEntry.finalPath);
                if settings.changeOwnerToCurrentUser or settings.changeOwnerTo:
                    fileName = Path(member.name).name
                    filePath = Path(fileEntry.finalPath, fileName)
                    if filePath.exists():
                        print(f"Changing this file owner to '{os.getlogin()}'")
                        if settings.changeOwnerToCurrentUser:
                            shutil.chown(filePath, os.getlogin())
                        else:
                            shutil.chown(filePath, settings.changeOwnerTo)





def main():
    settings = Settings()

    with RemoteFolder(Settings.folderToMound, Settings.testFolder) as localFolder:
        print(localFolder)
        with tarfile.open(f"{localFolder}{Settings.pathToArchive}", 'r') as archive:
            extract(settings, archive)


if __name__ == '__main__':
    print("************************\n")
    main()
    print("\n************************")
