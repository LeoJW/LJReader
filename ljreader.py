import sys
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import QTimer
from labjack import ljm
import pyqtgraph as pg
from collections import deque
from datetime import datetime

traceColors = [
    '#ffffff', '#ebac23', 
    '#b80058', '#008cf9',
    '#006e00', '#00bbad',
    '#d163e6', '#b24502',
    '#ff9287', '#5954d6',
    '#00c6f8', '#878500'
] # 12 color palette from http://tsitsul.in/blog/coloropt/

class LabJackStreamer(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # LabJack configuration
        self.handle = None
        self.scan_rate = 30000  # Hz (10 kHz - 30 kHz)
        self.num_channels = 2
        self.channels = ["AIN" + str(i) for i in range(self.num_channels)]
        self.channel_addresses = [ljm.nameToAddress(ch)[0] for ch in self.channels]
        
        # Buffer configuration
        self.plot_buffer_size = 5000  # points to display per channel
        self.read_interval = 50  # ms - read from stream every 50ms
        self.plot_update_interval = 100  # ms - update plot less frequently
        self.plot_downsample = 4  # Plot every Nth point for performance
        
        # Data storage
        self.plot_buffers = [deque(maxlen=self.plot_buffer_size) for _ in range(self.num_channels)]
        self.binary_file = None
        self.metadata_file = None
        self.total_samples_written = 0
        self.start_time = None
        
        # Separate timer for plot updates
        self.read_timer = QTimer()
        self.read_timer.timeout.connect(self.read_stream_data)
        
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_plots)
        
        # Performance tracking
        self.samples_received = 0
        self.last_perf_update = None
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("LabJack Data Streamer")
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Status label
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        
        # Create plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Voltage', 'V')
        self.plot_widget.setLabel('bottom', 'Sample', '#')
        self.plot_widget.addLegend()
        
        # Create plot curves for each channel
        self.curves = []
        for i, ch in enumerate(self.channels):
            curve = self.plot_widget.plot(pen=traceColors[i % len(traceColors)], name=ch)
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
            
            # Create binary file for data storage
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            binary_filename = f"{timestamp}.bin"
            metadata_filename = f"{timestamp}.meta"
            
            self.binary_file = open(binary_filename, 'wb')
            self.metadata_file = open(metadata_filename, 'w')
            
            # Write metadata
            self.start_time = datetime.now()
            metadata = f"""LabJack Data Stream
Start Time: {self.start_time.isoformat()}
Sample Rate: {self.scan_rate} Hz
Number of Channels: {self.num_channels}
Channels: {', '.join(self.channels)}
Data Format: Binary float64 (8 bytes per value)
Data Layout: Interleaved [ch0_sample0, ch1_sample0, ch0_sample1, ch1_sample1, ...]
"""
            self.metadata_file.write(metadata)
            self.metadata_file.flush()

            # Configure DAQ a little
            # Ensure triggered stream is disabled.
            ljm.eWriteName(self.handle, "STREAM_TRIGGER_INDEX", 0)
            # Enabling internally-clocked stream.
            ljm.eWriteName(self.handle, "STREAM_CLOCK_SOURCE", 0)
            # ljm.eWriteNames(self.handle, 1, "LJM_STREAM_AIN_BINARY", 1) # Need this to work but it doesn't seem to
            ljm.writeLibraryConfigS(ljm.constants.STREAM_AIN_BINARY, 1)
            
            # Configure and start stream
            scans_per_read = int(self.scan_rate * self.read_interval / 1000)
            scans_per_read = max(scans_per_read, 1)
            
            ljm.eStreamStart(
                self.handle,
                scans_per_read,
                self.num_channels,
                self.channel_addresses,
                self.scan_rate
            )
            
            print(f"Stream started at {self.scan_rate} Hz")
            print(f"Reading {scans_per_read} scans every {self.read_interval} ms")
            print(f"Binary file: {binary_filename}")
            
            # Reset counters
            self.total_samples_written = 0
            self.samples_received = 0
            self.last_perf_update = datetime.now()
            
            # Start the timers
            self.read_timer.start(self.read_interval)
            self.plot_timer.start(self.plot_update_interval)
            
            # Update button states
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            
            self.status_label.setText(f"Streaming at {self.scan_rate} Hz...")
            
        except Exception as e:
            print(f"Error starting stream: {e}")
            self.status_label.setText(f"Error: {e}")
            self.cleanup_stream()
    
    def read_stream_data(self):
        """Called periodically by QTimer to read data from stream"""
        try:
            # Read data from stream buffer
            ret = ljm.eStreamRead(self.handle)
            data = ret[0]  # Flat list of all channel data
            
            if len(data) == 0:
                return
            
            # Convert to numpy array and write directly to binary file
            # Data is already interleaved: [ch0, ch1, ch0, ch1, ...]
            data_array = np.array(data, dtype=np.float32)
            data_array.tofile(self.binary_file)
            
            # Track samples
            num_samples = len(data) // self.num_channels
            self.total_samples_written += num_samples
            self.samples_received += num_samples
            
            # Add to plot buffers (downsample for efficiency)
            for i in range(0, len(data), self.num_channels * self.plot_downsample):
                for ch_idx in range(self.num_channels):
                    if i + ch_idx < len(data):
                        self.plot_buffers[ch_idx].append(data[i + ch_idx])
            
            # Update performance stats periodically
            now = datetime.now()
            if (now - self.last_perf_update).total_seconds() >= 1.0:
                elapsed = (now - self.last_perf_update).total_seconds()
                sample_rate = self.samples_received / elapsed
                
                # Calculate file size
                file_size_mb = self.total_samples_written * self.num_channels * 8 / (1024 ** 2)
                
                self.status_label.setText(
                    f"Streaming: {sample_rate:.0f} samples/s | "
                    f"Total: {self.total_samples_written:,} scans | "
                    f"File: {file_size_mb:.1f} MB"
                )
                
                self.samples_received = 0
                self.last_perf_update = now
            
        except ljm.LJMError as e:
            if e.errorCode == ljm.errorcodes.NO_SCANS_RETURNED:
                # No data available yet, this is normal
                pass
            else:
                print(f"Stream error: {e}")
                self.status_label.setText(f"Stream error: {e}")
                self.stop_streaming()
        except Exception as e:
            print(f"Error reading stream: {e}")
            self.status_label.setText(f"Error: {e}")
            self.stop_streaming()
    
    def update_plots(self):
        """Update the plot curves with current buffer data (called less frequently)"""
        for i, curve in enumerate(self.curves):
            if len(self.plot_buffers[i]) > 0:
                curve.setData(self.plot_buffers[i])
    
    def stop_streaming(self):
        """Stop the stream and cleanup"""
        self.read_timer.stop()
        self.plot_timer.stop()
        
        # Write final metadata
        if self.metadata_file is not None:
            end_time = datetime.now()
            duration = (end_time - self.start_time).total_seconds() if self.start_time else 0
            
            final_metadata = f"""
End Time: {end_time.isoformat()}
Duration: {duration:.2f} seconds
Total Scans: {self.total_samples_written}
Actual Sample Rate: {self.total_samples_written / duration:.2f} Hz
"""
            self.metadata_file.write(final_metadata)
        
        self.cleanup_stream()
        
        # Update button states
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        self.status_label.setText(f"Stopped. Wrote {self.total_samples_written:,} scans.")
        print("Stream stopped")
    
    def cleanup_stream(self):
        """Cleanup LabJack connection and files"""
        try:
            if self.handle is not None:
                ljm.eStreamStop(self.handle)
                ljm.close(self.handle)
                self.handle = None
        except:
            pass
        
        if self.binary_file is not None:
            self.binary_file.close()
            self.binary_file = None
            
        if self.metadata_file is not None:
            self.metadata_file.close()
            self.metadata_file = None
    
    def closeEvent(self, event):
        """Handle window close event"""
        self.stop_streaming()
        event.accept()


def read_binary_data(filename, num_channels):
    """
    Utility function to read back the binary data file.
    
    Args:
        filename: Path to the .bin file
        num_channels: Number of channels in the recording
    
    Returns:
        numpy array of shape (num_scans, num_channels)
    """
    # Read all data
    data = np.fromfile(filename, dtype=np.float64)
    
    # Reshape to (num_scans, num_channels)
    num_scans = len(data) // num_channels
    data = data[:num_scans * num_channels]  # Trim any partial scan
    data = data.reshape((num_scans, num_channels))
    
    return data


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LabJackStreamer()
    window.show()
    
    sys.exit(app.exec())