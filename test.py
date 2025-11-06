import sys
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton
from PyQt6.QtCore import QTimer
from labjack import ljm
import pyqtgraph as pg
from collections import deque
from datetime import datetime

class LabJackStreamer(QMainWindow):
    def __init__(self):
        super().__init__()
        
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
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("LabJack Data Streamer")
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Voltage', 'V')
        self.plot_widget.setLabel('bottom', 'Sample', '#')
        self.plot_widget.addLegend()
        
        # Create plot curves for each channel
        self.curves = []
        colors = ['r', 'g', 'b', 'y']
        for i, ch in enumerate(self.channels):
            curve = self.plot_widget.plot(pen=colors[i], name=ch)
            self.curves.append(curve)
        
        layout.addWidget(self.plot_widget)
        
        # Control buttons
        self.start_btn = QPushButton("Start Streaming")
        self.start_btn.clicked.connect(self.start_streaming)
        layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop Streaming")
        self.stop_btn.clicked.connect(self.stop_streaming)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)
        
    def start_streaming(self):
        try:
            # Open LabJack
            self.handle = ljm.openS("ANY", "ANY", "ANY")
            
            # Open file for data storage
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.file_handle = open(f"labjack_data_{timestamp}.csv", 'w')
            
            # Write header
            header = "timestamp," + ",".join(self.channels) + "\n"
            self.file_handle.write(header)
            
            # Configure and start stream
            scans_per_read = int(self.scan_rate * self.read_interval / 1000)
            
            ljm.eStreamStart(
                self.handle,
                scans_per_read,
                self.num_channels,
                self.channel_addresses,
                self.scan_rate
            )
            
            print(f"Stream started at {self.scan_rate} Hz")
            print(f"Reading {scans_per_read} scans every {self.read_interval} ms")
            
            # Start the timer to read data
            self.read_timer.start(self.read_interval)
            
            # Update button states
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            
        except Exception as e:
            print(f"Error starting stream: {e}")
            self.cleanup_stream()
    
    def read_stream_data(self):
        """Called periodically by QTimer to read data from stream"""
        try:
            # Read data from stream buffer
            ret = ljm.eStreamRead(self.handle)
            data = ret[0]  # This is a flat list of all channel data
            
            # Reshape data: data comes as [ch0_sample0, ch1_sample0, ch0_sample1, ch1_sample1, ...]
            num_samples = len(data) // self.num_channels
            
            # Process each scan (set of samples across all channels)
            for i in range(num_samples):
                timestamp = datetime.now().timestamp()
                
                # Extract values for this scan
                scan_values = []
                for ch_idx in range(self.num_channels):
                    value = data[i * self.num_channels + ch_idx]
                    scan_values.append(value)
                    
                    # Add to plot buffer
                    self.plot_buffers[ch_idx].append(value)
                
                # Write to file
                line = f"{timestamp}," + ",".join(map(str, scan_values)) + "\n"
                self.file_handle.write(line)
            
            # Update plots
            self.update_plots()
            
        except ljm.LJMError as e:
            if e.errorCode == ljm.errorcodes.NO_SCANS_RETURNED:
                # No data available yet, this is normal
                pass
            else:
                print(f"Stream error: {e}")
                self.stop_streaming()
        except Exception as e:
            print(f"Error reading stream: {e}")
            self.stop_streaming()
    
    def update_plots(self):
        """Update the plot curves with current buffer data"""
        for i, curve in enumerate(self.curves):
            if len(self.plot_buffers[i]) > 0:
                curve.setData(list(self.plot_buffers[i]))
    
    def stop_streaming(self):
        """Stop the stream and cleanup"""
        self.read_timer.stop()
        self.cleanup_stream()
        
        # Update button states
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        print("Stream stopped")
    
    def cleanup_stream(self):
        """Cleanup LabJack connection and file"""
        try:
            if self.handle is not None:
                ljm.eStreamStop(self.handle)
                ljm.close(self.handle)
                self.handle = None
        except:
            pass
        
        if self.file_handle is not None:
            self.file_handle.close()
            self.file_handle = None
    
    def closeEvent(self, event):
        """Handle window close event"""
        self.stop_streaming()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LabJackStreamer()
    window.show()
    sys.exit(app.exec())

"""
## Key Implementation Details

### 1. **Timer-Based Reading**
- `QTimer` fires every `read_interval` ms (e.g., 100 ms)
- Each timeout calls `read_stream_data()` which uses `ljm.eStreamRead()` to grab accumulated samples from the LabJack's internal buffer

### 2. **Circular Buffer for Plotting**
- Using `collections.deque` with `maxlen` creates an automatic circular buffer
- Old data automatically drops off as new data arrives
- Efficient for maintaining a fixed-size rolling window

### 3. **Data Flow**
```
LabJack Hardware → LJM Buffer → eStreamRead() → Process & Save → Plot Buffer → Display

"""