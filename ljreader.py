# AMPS
# Assisted Motor Program Sorter (or Muscle Potential Sorter)
import json
import datetime
import os
import re
import scipy.io
import h5py
from labjack import ljm
from mainwindow_ui import Ui_MainWindow
import numpy as np
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtGui import (
    QAction, 
    QKeySequence, 
    QShortcut, 
    QIntValidator, 
    QDoubleValidator,
    QColor
)
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QLineEdit,
    QLabel
)
import pyqtgraph as pg
from settingsDialog import *
from dataModels import *
 
""" 
Main TODO / bugs:

"""

# Could set up to instead get names from files themselves
# But premature optimization = root of all evil
muscleNames = ['lax','lba','lsa','ldvm','ldlm','rdlm','rdvm','rsa','rba','rax']
filtEnableColor = '#73A843'
highlightColor = '#EEEEEE'
muscleColors = [
    "#94D63C", "#AE3FC3", "#FFBE24", "#66AFE6", "#E87D7A",
    "#C14434", "#2A4A78", "#E7AC1E", "#7D2D8C", "#6A992A"]
unitColors = [
    '#ffffff', '#ebac23', 
    '#b80058', '#008cf9',
    '#006e00', '#00bbad',
    '#d163e6', '#b24502',
    '#ff9287', '#5954d6',
    '#00c6f8', '#878500'
] # 12 color palette from http://tsitsul.in/blog/coloropt/
invalidColor = QColor(120,120,120,200)
unitKeys = ['0','1','2','3','4','5','6','7','8','9']
statusBarDisplayTime = 3000 # ms

class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        Ui_MainWindow.__init__(self)
        self.setupUi(self)
        self.traceDataModel = TraceDataModel()
        self._path_data = os.path.dirname(os.path.abspath(__file__))
        self._path_amps = os.path.dirname(os.path.abspath(__file__))
        
        # Traces plot (default run, uses default muscle names and colors)
        self.muscleColorsDict = {muscleNames[i] : muscleColors[i] for i in range(len(muscleNames))}
        self._activeIndex = 0
        self.traces = []
        self.setNewTraces()
        self.traceView.showGrid(x=True, y=True)
        
        #--- Main controls


        #--- Top toolbar menus
        # menu = self.menuBar()
        # open_action = QAction("Open", self)
        # open_action.setStatusTip("Open a new folder of data")
        # open_action.triggered.connect(self.onFileOpenClick)
        
        # file_menu = menu.addMenu("File")
        # settings_menu = menu.addMenu("Preferences")
        # # Note: naming the settings_menu and settings_action the same name for macOS
        # # triggers moving it to the more official Python > Preferences (Cmd + ,) location
        # # Not sure why, but it's nice so I'm leaving it
        # file_menu.addAction(open_action)
        # file_menu.addSeparator()
        # file_menu.addAction(load_action)
        # settings_menu.addAction(settings_action)
        # settings_menu.addSeparator()
        
        #--- Status bar
        self.fileLabel = QLabel('')
        self.statusBar.addPermanentWidget(self.fileLabel)
        
        #--- Settings dialog, main app settings
        self.settings = QtCore.QSettings('DickersonLab', 'LJReader')
        self.settingsDialog = SettingsDialog(self)
        self.setSettingsCache()
        
        #--- Keyboard shortcuts
        self.shortcutDict = {
            "Ctrl+O" : self.onFileOpenClick,
            "Ctrl+L" : self.onLoadPreviousClick,
            "Ctrl+S" : self.save,
        }
        self.shortcuts = []
        for keycombo, keyfunc in self.shortcutDict.items():
            self.shortcuts.append(QShortcut(QKeySequence(keycombo), self))
            self.shortcuts[-1].activated.connect(keyfunc)

        # LabJack configuration
        self.handle = None
        self.scan_rate = 1000  # Hz
        self.num_channels = 2
        self.channels = ["AIN0", "AIN1"]
        self.channel_addresses = [ljm.nameToAddress(ch)[0] for ch in self.channels]
        
        # Buffer configuration
        self.plot_buffer_size = 5000  # points to display
        self.read_interval = 100  # ms - how often to read from stream
        
        # Data storage
        self.plot_buffers = [deque(maxlen=self.plot_buffer_size) for _ in range(self.num_channels)]
        self.file_handle = None

        # Timer for reading data
        self.read_timer = QTimer()
        self.read_timer.timeout.connect(self.read_stream_data)


    #------------------------ Start stream handling ------------------------#
    
    def initiateStream(self):
        # Lock UI elements
        a=1
        # Initialize DAQ


    # Function to gather data, write to file (if recording) and update plot
    # must be on a timer, matched to a reasonable buffer
    
    
    def switchTrialDown(self):
        ti, mi = self.muscleTableModel.trialIndex, self._activeIndex
        if(ti == len(self.trialListModel.trials) - 1):
            self.trialSelectionChanged(0, ti)
            index = self.trialListModel.createIndex(0, 0)
            self.trialView.selectionModel().select(index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)
        else:
            self.trialSelectionChanged(ti + 1, ti)
            index = self.trialListModel.createIndex(ti+1, 0)
            self.trialView.selectionModel().select(index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)
    def switchTrialUp(self):
        ti, mi = self.muscleTableModel.trialIndex, self._activeIndex
        if(ti == 0):
            self.trialSelectionChanged(len(self.trialListModel.trials) - 1, ti)
            index = self.trialListModel.createIndex(len(self.trialListModel.trials) - 1, 0)
            self.trialView.selectionModel().select(index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)
        else:
            self.trialSelectionChanged(ti - 1, ti)
            index = self.trialListModel.createIndex(ti - 1, 0)
            self.trialView.selectionModel().select(index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)


    def changePCViewX(self, view):
        self.activePC[0] = view
        ti, mi = self.muscleTableModel.trialIndex, self._activeIndex
        self.spikeDataModel.updatePCA((ti,mi))
        self.updatePCView()

    def changePCViewY(self, view):
        self.activePC[1] = view
        ti, mi = self.muscleTableModel.trialIndex, self._activeIndex
        self.spikeDataModel.updatePCA((ti,mi))
        self.updatePCView()

    def setPCManual(self):
        PCX = int(self.pcaXValueInput.text())-1
        PCY = int(self.pcaYValueInput.text())-1
        self.changePCViewX(PCX)
        self.changePCViewY(PCY)



    # Shift the trace view by default 5% of whatever the current range is
    def panLeft(self, frac=0.05):
        range = self.traceView.getPlotItem().viewRange()
        shift = frac * (range[0][1] - range[0][0])
        self.traceView.setXRange(range[0][0]-shift, range[0][1]-shift, padding=0)
    def panRight(self, frac=0.05):
        range = self.traceView.getPlotItem().viewRange()
        shift = frac * (range[0][1] - range[0][0])
        self.traceView.setXRange(range[0][0]+shift, range[0][1]+shift, padding=0)
    # Zoom in or out on the x axis by default 10% of current range
    def xZoomIn(self, frac=0.05):
        range = self.traceView.getPlotItem().viewRange()
        shift = frac * (range[0][1] - range[0][0])
        self.traceView.setXRange(range[0][0]+shift, range[0][1]-shift, padding=0)
    def xZoomOut(self, frac=0.05):
        range = self.traceView.getPlotItem().viewRange()
        shift = frac * (range[0][1] - range[0][0])
        self.traceView.setXRange(range[0][0]-shift, range[0][1]+shift, padding=0)
    
    # def lineEditClearFocus(self):
    #     # Clear focus from LineEdit widgets
    #     if isinstance(self.sender(), QLineEdit):
    #         self.sender().clearFocus()
    
    #------------------------ Plot update functions ------------------------#
    # def updateWaveView(self):
    #     ti, mi = self.muscleTableModel.trialIndex, self._activeIndex
    #     if self.spikeDataModel._spikes[ti][mi].shape[0] <= 1:
    #         for w in self.waves:
    #             w.setData([], [], connect=np.array([1]))
    #         return
    #     unit = self.spikeDataModel._spikes[ti][mi][:,2]
    #     valid = self.spikeDataModel._spikes[ti][mi][:,3] == 1
    #     # Plot valid waveforms from each unit
    #     for u in range(10):
    #         mask = np.logical_and(valid, unit==u)
    #         if not np.any(mask):
    #             self.waves[u].setData([],[])
    #             continue
    #         nwaves = sum(mask)
    #         ydata = self.spikeDataModel._spikes[ti][mi][mask, 5:].ravel()
    #         xdata = np.tile(np.arange(self.settingsCache['waveformLength']), nwaves)
    #         singleConnected = np.ones(self.settingsCache['waveformLength'], dtype=np.int32)
    #         singleConnected[-1] = 0
    #         connected = np.tile(singleConnected, nwaves)
    #         self.waves[u].setData(xdata, ydata, connect=connected)
    #     # Plot invalid waveforms, if they exist
    #     mask = np.logical_not(valid)
    #     if not np.any(mask):
    #         self.waves[-1].setData([],[])
    #         return
    #     nwaves = sum(mask)
    #     ydata = self.spikeDataModel._spikes[ti][mi][mask, 5:].ravel()
    #     xdata = np.tile(np.arange(self.settingsCache['waveformLength']), nwaves)
    #     singleConnected = np.ones(self.settingsCache['waveformLength'], dtype=np.int32)
    #     singleConnected[-1] = 0
    #     connected = np.tile(singleConnected, nwaves)
    #     self.waves[-1].setData(xdata, ydata, connect=connected)
    
    
    def updateTraceView(self):
        selectedRowIndices = [item.row() for item in self.muscleView.selectionModel().selectedRows()]
        unselectedRowIndices = [i for i in set(range(len(self.muscleNames))) if i not in selectedRowIndices]
        # Plot selected traces
        for i,ind in enumerate(selectedRowIndices):
            self.traces[ind].setData(self.traceDataModel.get('time'), self.traceDataModel.get(self.muscleNames[ind]) + i)
        # Clear unselected traces
        for ind in unselectedRowIndices:
            self.traces[ind].setData([],[])
        # Update Y axis
        yax = self.traceView.getAxis('left')
        yax.setTicks([[(i, self.muscleNames[j]) for i,j in enumerate(selectedRowIndices)],[]])
        # Set active index as one of the selected traces
        if self._activeIndex not in selectedRowIndices and len(selectedRowIndices) > 0:
            self.setActiveTrace(selectedRowIndices[0])
    
    def onFileOpenClick(self):
        # Start one dir back from whatever last data dir was
        startDirGuess = os.path.join(self.settings.value('last_paths', ['~'], str)[0], '..')
        self._path_data = QFileDialog.getExistingDirectory(self, "Open Data Folder", startDirGuess)
        self.initializeDataDir()
    
    def onLoadPreviousClick(self):
        # Get paths, core variables from QSettings, use to populate app
        self._path_data, self._path_amps = self.settings.value('last_paths', [], str)
        self.initializeDataDir()
        
    def onSettingsClick(self):
        self.settingsDialog.exec()
        self.setSettingsCache()
    
    def setSettingsCache(self):
        self.settingsCache = {
            'waveformLength' : int(self.settings.value('waveformLength', '32')),
            'alignAt' : self.settings.value('alignAt', 'local maxima'),
            'deadTime' : int(self.settings.value('deadTime', '10')),
            'fractionPreAlign' : float(self.settings.value('fractionPreAlign', '0.4'))
        }
        setLength = int(self.settings.value('waveformLength', '32'))
        # If waveformLength in cache is equivalent to what was set, do nothing
        if not hasattr(self.spikeDataModel, '_spikes'):
            return
        if self.spikeDataModel._spikes[0][0].shape[1] == (5 + setLength):
            return
        cachedLength = self.spikeDataModel._spikes[0][0].shape[1] - 5
        # If waveformLength in cache was larger than what was set, reshape _spikes to make it smaller
        if self.spikeDataModel._spikes[0][0].shape[1] > (5 + setLength):
            change = cachedLength - setLength
            changeLeft = int(np.rint(change * self.settingsCache["fractionPreAlign"]))
            changeRight = int(change - changeLeft)
            for trialIndex, trial in enumerate(self.spikeDataModel._spikes):
                for muscleIndex, muscle in enumerate(trial):
                    holdArray = muscle[:, 0:5]
                    modifyArray = muscle[:, 5:]
                    modifyArray = modifyArray[:, changeLeft:-changeRight]
                    self.spikeDataModel._spikes[trialIndex][muscleIndex] = np.hstack((holdArray, modifyArray))
            return
        # If waveformLength in cache was smaller than what was set, reshape _spikes to make it bigger
        elif self.spikeDataModel._spikes[0][0].shape[1] < 5 + setLength:
            for trialIndex, trial in enumerate(self.spikeDataModel._spikes):
                for muscleIndex, muscle in enumerate(trial):
                    newArray = np.zeros((muscle.shape[0], 5 + setLength))
                    newArray[:, 0:5 + cachedLength] = muscle
                    self.spikeDataModel._spikes[trialIndex][muscleIndex] = newArray
            return

    
    def initializeDataDir(self):
        self.fileLabel.setText(os.path.basename(self._path_data))
        dir_contents = os.listdir(self._path_data)
        self._path_amps = os.path.join(self._path_data, 'amps')
        # If amps already exists, just load that
        if 'amps' in dir_contents:
            self.load()
            return
        # If no dir for amps in data dir
        # Make one, read contents of data, populate app
        os.mkdir(self._path_amps)
        # Grab list of trials
        trial_names = [f for f in dir_contents
                if '.mat' in f or '.h5' in f
                if 'twitch' not in f
                if 'FT' not in f
                if 'Control' not in f
                if 'quiet' not in f
                if 'empty' not in f]
        # Grab muscle names from first file. Assumes (requires) that all files have same muscle names and same layout
        muscleNames = []
        strippedChannels = []
        file = trial_names[0]
        if '.h5' in file:
            file_data = h5py.File(os.path.join(self._path_data, file), 'r')
            strippedChannels = [str(x).strip("[b'").strip("']") for x in file_data['names']]
            file_data.close()
            for name in strippedChannels:
                if bool(re.match(r'^[A-Z]', name[0])):
                    muscleNames.append(name)
        elif '.mat' in file:
            file_data = scipy.io.loadmat(os.path.join(self._path_data, file))
            for name in file_data['channelNames'][0]:
                stripName = str(name).strip("['").strip("']")
                if bool(re.match(r'^[A-Z]', stripName[0])):
                    muscleNames.append(stripName)
        self.muscleNames = muscleNames
        for i in range(len(self.muscleNames)):
            self.muscleNames[i] = self.muscleNames[i].lower()
        self.setNewTraces()
        trial_nums = [f.split('.')[0][-3:] for f in trial_names]
        trials = sorted(zip(trial_nums, trial_names))
        # Generate fresh (muscle, nspike) array
        self.trialListModel.trials = trials
        self.muscleTableModel._data = [[[m, 0, False, '_-_'] for m in self.muscleNames] for i in range(len(trials))]
        self.spikeDataModel.create(trials, self.muscleNames, waveformLength=self.settingsCache['waveformLength'])
        self.save()
        self.trialListModel.layoutChanged.emit()
        self.muscleTableModel.layoutChanged.emit()
    
    def load(self):
        try:
            # Load trial/muscle parameters
            with open(os.path.join(self._path_amps, 'trial_params.json'), 'r') as f:
                data = json.load(f)
                self.trialListModel.trials = data['trialListModel']
                self.muscleTableModel._data = data['muscleTableModel']
                self.trialListModel.layoutChanged.emit()
                self.muscleTableModel.layoutChanged.emit()
            # Load spike data
            muscles = [m[0] for m in self.muscleTableModel._data[0]]
            trials = [t[0] for t in self.trialListModel.trials]
            self.spikeDataModel.create(trials, muscles, waveformLength=self.settingsCache['waveformLength'])
            with open(os.path.join(self._path_amps, 'detection_params.json'), 'r') as f:
                data = json.load(f)
                self.spikeDataModel._params = data['detectFuncParams']
                self.spikeDataModel._filters = [[np.array(arr) for arr in sublist] for sublist in data['filters']]
                self.reassignedMuscles = data['reassigned muscles']
                self.reassignFromDict(self.reassignedMuscles)
                loaded_version = data['amps version']
                # Newest version (v >= 0.4) saves muscle names, but older versions don't
                if 'muscleNames' in data:
                    self.muscleNames = data['muscleNames']
                else:
                    self.muscleNames = muscleNames
                self.setNewTraces()
            with open(os.path.join(self._path_amps, 'detection_functions.pkl'), 'rb') as f:
                self.spikeDataModel._funcs = dill.load(f)
            data = np.genfromtxt(os.path.join(self._path_amps, 'spikes.txt'), delimiter=',')
            # Note: Muscles are numbered in numpy array according to their index/order in muscleTable
            # Assumes every trial for this folder follows same scheme as first trial
            if len(data) == 0:
                raise Exception('spikes.txt has 0 rows of data')
            # Versions before v0.3 didn't include spike sample/indices, drop in zeros instead
            if float(loaded_version[1:]) < 0.3: 
                data = np.hstack((data[:,0:3], np.zeros((data.shape[0],1)), data[:,3:]))
            for i,trial in enumerate(trials):
                for j,muscle in enumerate(muscles):
                        self.spikeDataModel.updateSpikes(
                            data[np.logical_and(data[:,0]==int(trial), data[:,1]==j), 2:],
                            (i,j)
                        )
        except Exception as error:
            self.statusBar.showMessage('Failed:' + repr(error), statusBarDisplayTime)
            pass
    
    def save(self):
        # Don't save if nothing happened
        if len(self.trialListModel.trials) == 0:
            return
        self.statusBar.showMessage('Saving...', statusBarDisplayTime)
        # Otherwise save all main paramters in different files
        with open(os.path.join(self._path_amps, 'trial_params.json'), 'w') as f:
            data = {
                'trialListModel' : self.trialListModel.trials,
                'muscleTableModel' : self.muscleTableModel._data
                }
            json.dump(data, f, indent=4, separators=(',',':'))
        with open(os.path.join(self._path_amps, 'detection_params.json'), 'w') as f:
            data = {
                'sorting date' : str(datetime.datetime.now()),
                'amps version' : 'v0.4',
                'sampling frequency' : self.traceDataModel._fs,
                'aligned at' : self.settingsCache['alignAt'],
                'reassigned muscles' : self.reassignedMuscles,
                'detectFuncParams' : self.spikeDataModel._params,
                'filters' : [[arr.tolist() for arr in sublist] for sublist in self.spikeDataModel._filters],
                'muscleNames' : self.muscleNames
            }
            json.dump(data, f, indent=4, separators=(',',':'))
        with open(os.path.join(self._path_amps, 'detection_functions.pkl'), 'wb') as f:
            dill.dump(self.spikeDataModel._funcs, f)
        # Put spike numpy arrays together into single array, save
        savelist = []
        for i, perTrialList in enumerate(self.spikeDataModel._spikes):
            trialNum = int(self.trialListModel.trials[i][0])
            for j, arr in enumerate(perTrialList):
                savelist.append(
                    np.concatenate((trialNum * np.ones((arr.shape[0],1)), j * np.ones((arr.shape[0],1)), arr), axis=1)
                )
        savedata = np.vstack(savelist)
        # Create header with column names, muscle numbering scheme
        # Note: Muscles are numbered in numpy array according to their index/order in muscleTable
        # Assumes every trial for this folder follows same scheme as first trial
        colNames = 'trial, muscle, time, sample, unit, valid, prespike, waveform \n'
        muscleScheme = ', '.join([str(i)+' = '+m[0] for (i,m) in enumerate(self.muscleTableModel._data[0])])
        np.savetxt(
            os.path.join(self._path_amps, 'spikes.txt'),
            savedata,
            fmt = ('%u', '%u', '%.18f', '%u', '%u', '%u', '%u', *('%.16f' for _ in range(self.settingsCache['waveformLength']))),
            delimiter=',',
            header=colNames + muscleScheme
        )
        self.statusBar.showMessage('file saved', statusBarDisplayTime)
    
    # Execute on app close
    def closeEvent(self, event):
        self.settings.setValue('last_paths', [self._path_data, self._path_amps])
        self.settings.sync()
        self.save()

def mouseDragEvent(ev):
    ev.accept()  # accept all buttons
    dif = (ev.pos() - ev.lastPos()) * -1

app = QtWidgets.QApplication([])
window = MainWindow()
window.show()
app.exec()