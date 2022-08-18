import os
import sys
from sys import exit
import subprocess
from subprocess import Popen
import re
import configparser
import ase
import time
import interfaceN2P2
import interfaceVASP
from dumpMerger import merge

class Unbuffered(object):
   def __init__(self, stream):
       self.stream = stream
   def write(self, data):
       self.stream.write(data)
       self.stream.flush()
   def writelines(self, datas):
       self.stream.writelines(datas)
       self.stream.flush()
   def __getattr__(self, attr):
       return getattr(self.stream, attr)
# In order to make python output be immediately written to the slurm output file
sys.stdout = Unbuffered(sys.stdout)

def readLASP2():
    global lasp2
    vars = config['LASP2']
    for key in vars:
        if key == 'numseeds':
            try:
                lasp2[key] = int(vars[key])
            except:
                print('Invalid value for variable: ' +key)
                exit(1)
        elif key == 'numprocs':
            try:
                lasp2[key] = int(vars[key])
            except:
                print('Invalid value for variable: ' + key)
                exit(1)
        elif key == 'exec':
            try:
                lasp2[key] = str(vars[key])
            except:
                print('Invalid value for variable: ' + key)
                exit(1)
        elif key == 'dirpotentials':
            try:
                lasp2[key] = str(vars[key])
                if not os.path.isdir(lasp2[key]):
                    print('Directory of potentials was not found')
                    raise Exception('Directory not found')
                numSeeds = lasp2['numseeds']
                for i in range(1, numSeeds+1):
                    if not os.path.isdir(os.path.join(lasp2[key], 'Seed'+str(i))):
                        print('Seed'+str(i)+' not found')
                        raise Exception('Seed not found')
            except:
                print('Invalid value for variable: ' +key)
        if key == 'dirdatabase':
            try:
                lasp2[key] = str(vars[key])
                if not os.path.isfile(lasp2[key]):
                    print('n2p2 database file could not be found: '+lasp2[key])
                    raise Exception('File error')
            except:
                print('Invalid value for variable: ' + key)
        else:
            print('Invalid variable: '+key)
            exit(1)

# Read input from lasp2.ini or another file indicated by the user
inputFile = 'lasp2.ini'
dirInterface = '###INTERFACE###'
if not os.path.isfile(dirInterface):
    print('Binary file for LAMMPS interface could not be found: '+dirInterface)
    raise Exception('File error')
for i in range(len(sys.argv)):
    if sys.argv[i] == '-i':
        try:
            inputFile = sys.argv[i+1]
            if not os.path.isfile(inputFile):
                print('Input file could not be found: '+inputFile)
                raise Exception('File error')
        except:
            print('No valid input parameter after option -i')
            exit(1)
    if sys.argv[i] == '--merge':
        numDumps = 0
        nameDump = ''
        outputDump = ''
        if len(sys.argv) > i+4:
            print('Error: more parameters than expected')
            print('Expected input:')
            print('--merge (number of dumps) (name of dumps) (name of output)')
            print("--merge 10 'dump*.lammpstrj' dumpComplete.lammpstrj")
            print('Name of dump files has to be given inside quotes, as to avoid using regular expressions')
        try:
            numDumps = int(sys.argv[i+1])
            nameDump = str(sys.argv[i+2])
            outputDump = str(sys.argv[i+3])
        except:
            print('Wrong input for merging command')
            print('Expected input:')
            print('--merge (number of dumps) (name of dumps) (name of output)')
            print("--merge 10 'dump*.lammpstrj' dumpComplete.lammpstrj")
            exit(1)
        merge(numDumps, nameDump, outputDump)
        exit()

# Dictionary where configuration variables will be stored
lasp2 = dict()
# Read input data for the interface
config = configparser.ConfigParser()
config.read(inputFile)
for section in config:
    if section == 'LASP2':
        readLASP2()
    elif section == 'LAMMPS':
        continue
    elif section == 'N2P2':
        interfaceN2P2.readN2P2(inputFile)
    elif section == 'VASP':
        interfaceVASP.readVASP(inputFile)
    elif section == 'DEFAULT':
        if len(config[section]) > 0:
            print('Undefined section found: DEFAULT')
            exit(1)
    else:
        print('Undefined section found: ' + section)
        exit(1)

potDirs = 'Training/' #Training files produced during the simulation
os.makedirs(potDirs, exist_ok=True)
os.makedirs('Restart', exist_ok=True)
potInitial = lasp2['dirpotentials']
os.system('cp -r '+potInitial+' '+potDirs+'Potentials')
os.system('cp '+lasp2['dirdatabase']+' Training/complete0.data')
trainings = 1

# Begin simulation
lammpsRun = Popen(lasp2['exec']+' -n '+str(lasp2['numprocs'])+' '+dirInterface+' --start -config '+inputFile+' -iteration '+str(trainings)+' > lasp2_'+str(trainings)+'.out', shell=True, stderr=subprocess.PIPE)
lammpsRun.wait()
exitErr = lammpsRun.stderr.read().decode()
print('LAMMPS exited with stderr: '+exitErr)
while True:
    if re.match('^50', exitErr): #Exit code returned when the flag for training is activated
        print('Performing DFT calculations         Iteration: '+str(trainings))
        interfaceVASP.compute(lasp2['exec'], trainings, lasp2['numprocs'])
        print('Performing NNP training             Iteration: '+str(trainings))
        interfaceN2P2.training(lasp2['exec'], potDirs, trainings, lasp2['numseeds'], lasp2['numprocs'])
        trainings += 1
        lammpsRun = Popen(lasp2['exec']+' -n '+str(lasp2['numprocs'])+' '+dirInterface+' --restart -config '+inputFile+' -iteration '+str(trainings)+' > lasp2_'+str(trainings)+'.out', shell=True, stderr=subprocess.PIPE)
        lammpsRun.wait()
        exitErr = lammpsRun.stderr.read().decode()
    else:
        break
if not re.match('^50', exitErr):
    print('LAMMPS interface exited successfully')
    merge(trainings-1, 'Restart/dump*.lammpstrj', 'Restart/dumpComplete.lammpstrj')