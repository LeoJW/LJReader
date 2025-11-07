import sys
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import QTimer
from labjack import ljm
import pyqtgraph as pg
from datetime import datetime

traceColors = [
    '#ffffff', '#ebac23', 
    '#b80058', '#008cf9',
    '#006e00', '#00bbad',
    '#d163e6', '#b24502',
    '#ff9287', '#5954d6',
    '#00c6f8', '#878500'
]

class LabJackStreamer(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # LabJack configuration
        self.handle = None
        self.scan_rate = 30000  # Hz
        self.num_channels = 4
        self.channels = ["AIN" + str(i) for i in range(self.num_channels)]
        self.channel_addresses = [ljm.nameToAddress(ch)[0] for ch in self.channels]
        
        # Buffer configuration
        self.plot_buffer_size = 1000  # points to display per channel
        self.read_interval = 100  # ms - read from stream every x ms
        self.plot_update_interval = 500  # ms - Increase for better performance
        self.plot_downsample = 4  # Increase for better performance, plot every nth point
        
        # Use numpy arrays instead of deques for better performance
        self.plot_buffers = [np.zeros(self.plot_buffer_size, dtype=np.float32) 
                            for _ in range(self.num_channels)]
        self.buffer_indices = [0] * self.num_channels  # Track write position
        self.buffer_full = [False] * self.num_channels  # Track if buffer has wrapped
        
        self.binary_file = None
        self.metadata_file = None
        self.total_samples_written = 0
        self.start_time = None
        
        # Separate timers
        self.read_timer = QTimer()
        self.read_timer.timeout.connect(self.read_stream_data)
        
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_plots)
        
        # Performance tracking
        self.samples_received = 0
        self.last_perf_update = None
        
        # Plot data cache to avoid creating new arrays every update
        self.x_data = np.arange(self.plot_buffer_size)
        
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("LabJack Data Streamer")
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Status label
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        
        # Create plot widget with optimizations
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Voltage', 'V')
        self.plot_widget.setLabel('bottom', 'Sample', '#')
        self.plot_widget.addLegend()
        
        # Disable auto-range for better performance
        self.plot_widget.enableAutoRange(False)
        self.plot_widget.setRange(xRange=[0, self.plot_buffer_size], yRange=[-10, 10])
        
        # Reduce antialiasing for performance
        self.plot_widget.setAntialiasing(False)
        
        # Create plot curves for each channel
        self.curves = []
        for i, ch in enumerate(self.channels):
            curve = self.plot_widget.plot(
                pen=pg.mkPen(color=traceColors[i % len(traceColors)], width=1),
                name=ch
            )
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
Data Format: Binary float32 (4 bytes per value)
Data Layout: Interleaved [ch0_sample0, ch1_sample0, ch0_sample1, ch1_sample1, ...]
"""
            self.metadata_file.write(metadata)
            self.metadata_file.flush()

            # Configure DAQ
            # Resolution index can be set up to 4 when sampling 4 channels at 30kHz. 
            # Setting to zero auto-selects best available resolution
            configNames = ["STREAM_RESOLUTION_INDEX", "STREAM_TRIGGER_INDEX", "STREAM_CLOCK_SOURCE"]
            configValues = [0, 0, 0]
            ljm.eWriteNames(self.handle, len(configNames), configNames, configValues)
            # ljm.writeLibraryConfigS(ljm.constants.STREAM_AIN_BINARY, 1)
            
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
            
            # Reset counters and buffers
            self.total_samples_written = 0
            self.samples_received = 0
            self.last_perf_update = datetime.now()
            self.buffer_indices = [0] * self.num_channels
            self.buffer_full = [False] * self.num_channels
            
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
            
            data_array = np.array(data, dtype=np.float32)
            # Write directly to binary file
            data_array.tofile(self.binary_file)
            
            # Track samples
            num_samples = len(data) // self.num_channels
            self.total_samples_written += num_samples
            self.samples_received += num_samples
            
            # Update plot buffers
            # Downsample and separate channels
            for ch_idx in range(self.num_channels):
                # Extract channel data with downsampling
                ch_data = data_array[ch_idx::self.num_channels * self.plot_downsample]
                
                if len(ch_data) > 0:
                    # Efficiently update circular buffer
                    buf_idx = self.buffer_indices[ch_idx]
                    buf_size = self.plot_buffer_size
                    
                    # How many samples can we write before wrapping?
                    space_to_end = buf_size - buf_idx
                    
                    if len(ch_data) <= space_to_end:
                        # All data fits before wrap
                        self.plot_buffers[ch_idx][buf_idx:buf_idx + len(ch_data)] = ch_data
                        self.buffer_indices[ch_idx] = (buf_idx + len(ch_data)) % buf_size
                    else:
                        # Need to wrap
                        self.plot_buffers[ch_idx][buf_idx:] = ch_data[:space_to_end]
                        remainder = len(ch_data) - space_to_end
                        self.plot_buffers[ch_idx][:remainder] = ch_data[space_to_end:]
                        self.buffer_indices[ch_idx] = remainder
                        self.buffer_full[ch_idx] = True
            
            # Update performance stats periodically
            now = datetime.now()
            if (now - self.last_perf_update).total_seconds() >= 1.0:
                # Calculate file size
                file_size_mb = self.total_samples_written * self.num_channels * 4 / (1024 ** 2)
                
                self.status_label.setText(
                    f"Total: {self.total_samples_written:,} scans | "
                    f"File: {file_size_mb:.1f} MB | "
                    f"Device backlog: {ret[1]} samples | "
                    f"LJM backlog: {ret[2]} samples | "
                )
                
                self.samples_received = 0
                self.last_perf_update = now
            
        except ljm.LJMError as e:
            if e.errorCode == ljm.errorcodes.NO_SCANS_RETURNED:
                pass  # No data available yet, this is normal
            else:
                print(f"Stream error: {e}")
                self.status_label.setText(f"Stream error: {e}")
                self.stop_streaming()
        except Exception as e:
            print(f"Error reading stream: {e}")
            self.status_label.setText(f"Error: {e}")
            self.stop_streaming()
    
    def update_plots(self):
        """Update the plot curves with current buffer data"""
        for i, curve in enumerate(self.curves):
            # Only update if we have data
            if self.buffer_indices[i] > 0 or self.buffer_full[i]:
                if self.buffer_full[i]:
                    # Buffer has wrapped - reorder to show continuous data
                    idx = self.buffer_indices[i]
                    # Roll the data so newest is at the end
                    display_data = np.roll(self.plot_buffers[i], -idx)
                    curve.setData(display_data)
                else:
                    # Buffer not yet full - just show what we have
                    curve.setData(self.plot_buffers[i][:self.buffer_indices[i]])
    
    def stop_streaming(self):
        """Stop the stream and cleanup"""
        # TODO: Keep running read_timer until LJM buffer is empty
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
    # Read all data (note: changed to float32 to match new format)
    data = np.fromfile(filename, dtype=np.float32)
    
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