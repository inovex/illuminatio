import urllib.request
import os
import tarfile
import shutil

evalVersion = '1.1.0'
# ToDo Change back to https://github.com/ahmetb/kubernetes-network-policy-recipes
url = 'https://github.com/MaxBischoff/kubernetes-network-policy-recipes/archive/v' + evalVersion + '.tar.gz'
targetFolder = './tmp/evaluation_set'
versionFile = os.path.join(targetFolder, "version_" + evalVersion)
evaluationDir = os.path.join(targetFolder, 'kubernetes-network-policy-recipes-' + evalVersion, "")


def downloadEvaluationSet():
    file_tmp = urllib.request.urlretrieve(url, filename=None)[0]
    tar = tarfile.open(file_tmp)
    tar.extractall(targetFolder)
    # create a file with version as name
    open(versionFile, 'a').close()


if not os.path.isdir(targetFolder):
    # download evaluation set and extract it to targetFolder
    downloadEvaluationSet()
elif not os.path.exists(versionFile):
    # new version set, remove contents and update
    shutil.rmtree(targetFolder)
    downloadEvaluationSet()

print(evaluationDir)
