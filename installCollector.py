#! /usr/bin/python3

import os
import re
import pwd
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
    symLinkPath: str = ""  # what to link it to - TODO
    regex: re.Pattern = None


class Settings:
    class SettingsInitError(Exception):
        pass

#******************************************************************************************************************************
#********************************** SETTINGS START  ***************************************************************************
#******************************************************************************************************************************

    collectorVersion = "3.0.5-develop"
    osVersion = "Ubuntu20_04LTS"
    llvm = True
    llvmPattern = r".*/[^/]*llvm[^/]*$"

    changeOwnerToCurrentUser = True
    changeOwnerTo = ""
    folderToMount = "//collector-build.initi/build_repo/Develop/"

    files = [
        FileEntry(pattern = r"solo-platform-0\.1\.0", finalPath = "../test/",     renameTo = "platform",     symLinkPath = "platform" ),
        FileEntry(pattern = r"solo-jsonrpc-0\.1\.0",  finalPath = "../test/",     renameTo = "solo-jsonrpc", symLinkPath = "" ),
        FileEntry(pattern = r"lib[\w\.\-]*$",         finalPath = "../test/lib/", renameTo = "",             symLinkPath = "" )
    ]

#******************************************************************************************************************************
#********************************** SETTINGS END ******************************************************************************
#******************************************************************************************************************************

    def __init__(self):
        self.printer = _SameLinePrinter()
        self.checkUserExistance()
        self.compileRegexes()

    def checkUserExistance(self):
        if self.changeOwnerTo != "":
            try:
                pwd.getpwnam(self.changeOwnerTo)
            except KeyError as err:
                raise self.SettingsInitError(f"User '{self.changeOwnerTo}' does not exist.")

    def compileRegexes(self):
        try:
            self.llvmRegex = re.compile(self.llvmPattern)
        except re.error as e:
            raise self.SettingsInitError(f"Error in llvm regex pattern: '{self.llvmPattern}'")

        for entry in self.files:
            try:
                entry.regex = re.compile(f"\\./{entry.pattern}")
            except re.error as e:
                raise self.SettingsInitError(f"Error in regex pattern: '{entry.pattern}'")


class _Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(_Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class _SameLinePrinter(metaclass=_Singleton):
    def __init__(self):
        self._maxSize = 0
        self._stopped = True

    def print(self, printString):
        printStringLength = len(printString)
        if (printStringLength > self._maxSize):
            self._maxSize = printStringLength
        for i in range(self._maxSize - printStringLength):
            printString += " "
        print(printString, end='\r')
        self._stopped = False

    def clear(self):
        if not self._stopped:
            printingString = ""
            for i in range(self._maxSize):
                printingString += " "
            self._maxSize = 0
            print(printingString, end='\r')
            self._stopped = True

    def stop(self):
        if not self._stopped:
            self._maxSize = 0
            print("")
            self._stopped = True


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


class FilesExtractor:
    def __init__(self, settings, archive):
        self.settings = settings
        self.archive = archive
        self.filesProcessed = 0

    def extract(self):
        self.settings.printer.print(f"Getting archive files list (it may take a while)")
        archiveMembers = self.archive.getmembers()

        self.filesProcessed = 0

        for fileEntry in self.settings.files:
            for member in archiveMembers:
                if not member.isdir() and fileEntry.regex.match(member.name):
                    self.settings.printer.print(f"({self.filesProcessed + 1}) Extracting '{member.name}' to '{fileEntry.finalPath}'")
                    self.archive.extract(member, fileEntry.finalPath);
                    fileName = Path(member.name).name
                    filePath = Path(fileEntry.finalPath, fileName)
                    self.changeFileOwner(filePath)
                    filePath = self.renameFile(filePath, fileEntry)
                    self.genSymlink(filePath, fileEntry)
                    self.filesProcessed += 1

        self.settings.printer.print(f"Files extracted: {self.filesProcessed}")
        self.settings.printer.stop()


    def changeFileOwner(self, filePath):
        if filePath.exists() and (self.settings.changeOwnerToCurrentUser or self.settings.changeOwnerTo):
            self.settings.printer.print(f"({self.filesProcessed + 1}) Changing '{filePath.name}' owner to '{os.getlogin()}'")
            if self.settings.changeOwnerToCurrentUser:
                shutil.chown(filePath, os.getlogin())
            else:
                shutil.chown(filePath, self.settings.changeOwnerTo)


    def renameFile(self, filePath, fileEntry):
        if filePath.exists() and fileEntry.renameTo:
            newFile = Path(filePath.parent, fileEntry.renameTo)
            self.settings.printer.print(f"({self.filesProcessed + 1}) Renaming '{filePath.name}' to '{newFile.name}'")
            filePath.rename(newFile)
            return newFile
        else:
            return filePath

    def genSymlink(self, filePath, fileEntry):
        if filePath.exists() and fileEntry.symLinkPath:
            symLinkPath = Path(fileEntry.symLinkPath)
            if symLinkPath.exists():
                os.remove(symLinkPath)
            symLinkPath.symlink_to(filePath)
            self.changeFileOwner(symLinkPath)


def getArchivePath(settings, remoteFolder):
    archivePath = Path(remoteFolder, settings.collectorVersion)
    if not archivePath.exists():
        settings.printer.print(f"Could not find collector version folder: '{settings.collectorVersion}' in '{archivePath.parent}'")
        settings.printer.stop()
        return None

    archivePath = Path(archivePath, settings.osVersion)
    if not archivePath.exists():
        settings.printer.print(f"Could not find os version folder: '{settings.collectorVersion}' in '{archivePath.parent}'")
        settings.printer.stop()
        return None

    archivePath = max(archivePath.iterdir())

    for archiveFile in archivePath.iterdir():
        if settings.llvm and settings.llvmRegex.match(f'{archiveFile}'):
            return archiveFile
        elif not settings.llvm and not settings.llvmRegex.match(f'{archiveFile}'):
            return archiveFile
    return None




def main():
    try:
        settings = Settings()
    except Settings.SettingsInitError as err:
        print(err)
        return err

    with RemoteFolder(Settings.folderToMount, os.getcwd()) as localFolder:
        archivePath = getArchivePath(settings, localFolder)
        print(archivePath)
        if archivePath:
            with tarfile.open(archivePath, 'r') as archive:
                FilesExtractor(settings, archive).extract()

    settings.printer.stop()


if __name__ == '__main__':
    main()
