#! /usr/bin/python3

import os
import re
import pwd
import json
import shutil
import tarfile
import argparse
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
    regex: re.Pattern = None


class Settings:
    class SettingsInitError(Exception):
        pass

    defaultSettings = {
        "collectorVersion" : "",
        "osVersion" : "",
        "llvm" : False,
        "changeOwnerToCurrentUser" : False,
        "changeOwnerTo" : "",
        "folderToMount" : "",
        "filesToExtract" : [
            {"pattern" : "regex_of_file_name_in_archive", "finalPath" : "folder_to_extract_to", "renameTo" : "", "symLinkPath" : ""}
        ]
    }

    llvmPattern = r".*/[^/]*llvm[^/]*$"

    def __init__(self, configFileName):
        if not Path(configFileName).exists():
            with open(configFileName, 'w') as configFile:
                json.dump(self.defaultSettings, configFile)
                shutil.chown(configFileName, os.getlogin())
                self.SettingsInitError(f"Default config file '{configFileName}' was created, edit it before starting script")
        else:
            with open(configFileName, 'r') as configFile:
                config = json.load(configFile)
                try:
                    self.collectorVersion         = config["collectorVersion"]
                    self.osVersion                = config["osVersion"]
                    self.llvm                     = config["llvm"]
                    self.changeOwnerToCurrentUser = config["changeOwnerToCurrentUser"]
                    self.changeOwnerTo            = config["changeOwnerTo"]
                    self.folderToMount            = config["folderToMount"]
                    self.files = []
                    for entry in config["filesToExtract"]:
                        self.files.append(FileEntry(pattern = entry["pattern"], finalPath = entry["finalPath"], renameTo = entry["renameTo"], symLinkPath = entry["symLinkPath"]))
                except Exception as exception:
                    self.SettingsInitError(f"Error while extracting config data from '{configFileName}':\n{exception}")

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
            self.settings.printer.print(f"({self.filesProcessed + 1}) Linking '{symLinkPath.name}' to '{filePath.name}'")
            self.changeFileOwner(symLinkPath)


def getArchivePath(settings, remoteFolder):
    archivePath = Path(remoteFolder, settings.collectorVersion)
    if not archivePath.exists():
        settings.printer.print(f"Could not find collector version folder: '{settings.collectorVersion}' in '{archivePath.parent}'")
        settings.printer.stop()
        return None

    archivePath = Path(archivePath, settings.osVersion)
    if not archivePath.exists():
        settings.printer.print(f"Could not find os version folder: '{settings.osVersion}' in '{archivePath.parent}'")
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
    parser = argparse.ArgumentParser(description="Extracting files stated in config, renaming and creating symlinks if necessery. Should run under 'sudo'.")
    parser.add_argument("-c", "--config", default="installCollectorConfig.json", help="path to config file")
    args = parser.parse_args()
    settings = None

    try:
        settings = Settings(configFileName=args.config)
    except Settings.SettingsInitError as err:
        print(err)
        return err

    with RemoteFolder(settings.folderToMount, os.getcwd()) as localFolder:
        archivePath = getArchivePath(settings, localFolder)
        if archivePath:
            with tarfile.open(archivePath, 'r') as archive:
                extractor = FilesExtractor(settings, archive)
                extractor.extract()
                settings.printer.print(f"Files extracted: {extractor.filesProcessed} from '{archivePath}'")

    settings.printer.stop()


if __name__ == '__main__':
    main()
