import numpy as np
from scipy.signal import sosfiltfilt
from PyQt6 import QtCore
from PyQt6.QtGui import QColor

class TraceDataModel():
    def __init__(self, channelNames=[''], matrix=np.zeros((1,1)), *args, **kwargs):
        self.setAll(channelNames, matrix)
        self._replaceMuscles = {}
    
    def setAll(self, channelNames, matrix):
        self._names = channelNames
        # Identify dimension of matrix that matches length of names
        if len(self._names) in matrix.shape:
            # Arrange so channel dimension always on rows
            if matrix.shape.index(len(self._names)) == 1:
                matrix = matrix.T
        else:
            raise ValueError(f"Gave {len(self._names)} names but data matrix has no matching dimension")
        # Store two copies of the data: an original master, and processed form
        self._maindata = {}
        self._filtdata = {}
        for i,n in enumerate(self._names):
            self._maindata[n] = matrix[i,:].reshape(-1)
            self._filtdata[n] = matrix[i,:].reshape(-1)
        self.normalize()
        # If no time channel, make fake one
        if 'time' not in self._names:
            self._maindata['time'] = np.arange(matrix.shape[1])
            self._filtdata['time'] = np.arange(matrix.shape[1])
        # Grab sample rate. Takes most common diff of first 10 time samples. Use 1 if there's basically no data
        self._fs = 1.0
        if len(self._maindata['time']) >= 10:
            diffs = np.diff(self._maindata['time'][0:10])
            unique, counts = np.unique(diffs, return_counts=True)
            self._fs = 1 / unique[np.argmax(counts)]
    def setReplace(self, source, target):
        if source not in self._names or target not in self._names:
            return
        self._replaceMuscles[target] = source
        self._filtdata[target] = self._maindata[source]
    def clearReplace(self, target):
        self._filtdata[target] = self._maindata[target]
        self._replaceMuscles = {}
    def get(self, name):
        # Always return processed form, even if no processing
        return self._filtdata[name]
    def normalize(self, name=None):
        # Do all if no specific specified (except time!)
        if name == None:
            name = [n for n in self._names if 'time' not in n.lower()]
        # If only one specified make list
        elif isinstance(name, str): 
            name = [name]
        # Run normalization on all specified
        for n in name:
            max, min = self._filtdata[n].max(), self._filtdata[n].min()
            if max != min:
                self._filtdata[n] /= (max - min)
    def rescale(self, factor=1):
        for n in self._names:
            self._filtdata[n] *= factor
    def filter(self, name, filtsos):
        if isinstance(name, str):
            name = [name]
        for n in name:
            self._filtdata[n] = sosfiltfilt(filtsos, self._filtdata[n])
    def restore(self, name):
        if isinstance(name, str):
            name = [name]
        for n in name:
            if n in self._replaceMuscles.keys():
                self._filtdata[n] = self._maindata[self._replaceMuscles[n]]
            else:
                self._filtdata[n] = self._maindata[n]
