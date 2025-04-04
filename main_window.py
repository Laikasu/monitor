from PySide6.QtCore import QStandardPaths, QDir, QTimer, QEvent, QFileInfo, Qt, Signal, QThread, QWaitCondition, QMutex, QTemporaryFile
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent, QIcon, QImage
from PySide6.QtWidgets import QMainWindow, QMessageBox, QLabel, QApplication, QFileDialog, QToolBar, QPushButton, QInputDialog

import os
import numpy as np
import tifffile as tiff
import cv2
import time
import yaml

# Stage
from pymmcore_plus import CMMCorePlus
# Camera
import imagingcontrol4 as ic4
# Laser
from nktlaser import Laser

from widgets import VideoView, SweepDialog
import processing as pc
from camera import Camera

from functools import partial




class PersistentWorkerThread(QThread):
    def __init__(self, func):
        super().__init__()
        self.func = func


class MainWindow(QMainWindow):
    new_processed_frame = Signal(np.ndarray)
    def __init__(self):
        application_path = os.path.abspath(os.path.dirname(__file__)) + os.sep
        QMainWindow.__init__(self)
        self.setWindowIcon(QIcon(application_path + '/images/tis.ico'))

        # Setup stage
        # Setup microscope connection

        mm_dir = 'C:/Program Files/Micro-Manager-2.0'
        self.setup_micromanager(mm_dir)

        self.laser = Laser(self)
        self.laser.changedState.connect(self.update_controls)
        
        self.grid = False
        self.got_image_mutex = QMutex()
        self.got_image = QWaitCondition()

        self.aquiring = False
        self.aquiring_mutex = QMutex()

        self.temp_video_file = None
        

        # Make sure the %appdata%/demoapp directory exists
        appdata_directory = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        picture_directory = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        video_directory = QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)
        QDir(appdata_directory).mkpath('.')
        

        self.data_directory = picture_directory + '/Data'
        QDir(self.data_directory).mkpath('.')
        self.backgrounds_directory = picture_directory + '/Backgrounds'
        QDir(self.backgrounds_directory).mkpath('.')
        self.save_videos_directory = video_directory
        

        self.video_view = VideoView(self)
        self.video_view.roi_set.connect(self.update_roi)
        self.move_stage_worker = PersistentWorkerThread(self.move_stage)
        self.video_view.move_stage.connect(self.move_stage_worker.func)

        self.camera = Camera(self)
        self.camera.new_frame.connect(self.update_display)
        self.camera.state_changed.connect(self.update_controls)
        self.camera.opened.connect(self.video_view.set_size)
        self.camera.opened.connect(self.init_roi)
        

        self.background: np.ndarray = None
        self.subtract_background = False

        self.createUI()
        self.update_controls()
        self.camera.reload_device()
    

    def setup_micromanager(self, mm_dir):
        application_path = os.path.abspath(os.path.dirname(__file__)) + os.sep
        self.xy_stage = None
        self.z_stage = None
        
        self.mmc = CMMCorePlus.instance()
        try:
            self.mmc.setDeviceAdapterSearchPaths([mm_dir])
            self.mmc.loadSystemConfiguration(os.path.join(application_path, 'MMConfig.cfg'))
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'failed to load mm config: \n{e}')
        else:
            self.z_stage = self.mmc.getFocusDevice()
            self.xy_stage = self.mmc.getXYStageDevice()
            
    def createUI(self):
        self.resize(1024, 768)

        #=========#
        # Actions #
        #=========#
        application_path = os.path.abspath(os.path.dirname(__file__)) + os.sep
        
        self.device_select_act = QAction(QIcon(application_path + 'images/camera.png'), '&Select', self)
        self.device_select_act.setStatusTip('Select a video capture device')
        self.device_select_act.setShortcut(QKeySequence.Open)
        self.device_select_act.triggered.connect(partial(self.camera.onSelectDevice, self))

        self.device_properties_act = QAction(QIcon(application_path + 'images/imgset.png'), '&Properties', self)
        self.device_properties_act.setStatusTip('Show device property dialog')
        self.device_properties_act.triggered.connect(partial(self.camera.onDeviceProperties, self))

        self.device_driver_properties_act = QAction('&Driver Properties', self)
        self.device_driver_properties_act.setStatusTip('Show device driver property dialog')
        self.device_driver_properties_act.triggered.connect(partial(self.camera.onDeviceDriverProperties, self))

        self.start_live_act = QAction(QIcon(application_path + 'images/livestream.png'), '&Live Stream', self)
        self.start_live_act.setStatusTip('Start and stop the live stream')
        self.start_live_act.setCheckable(True)
        self.start_live_act.triggered.connect(self.camera.startStopStream)

        self.close_device_act = QAction('Close', self)
        self.close_device_act.setStatusTip('Close the currently opened device')
        self.close_device_act.setShortcuts(QKeySequence.Close)
        self.close_device_act.triggered.connect(self.camera.onCloseDevice)

        self.set_roi_act = QAction('Select ROI', self)
        self.set_roi_act.setStatusTip('Draw a rectangle to set ROI')
        self.set_roi_act.setCheckable(True)
        self.set_roi_act.triggered.connect(lambda: self.toggle_mode('roi'))

        self.move_act = QAction('Move', self)
        self.move_act.setStatusTip('Move the sample by dragging the view')
        self.move_act.setCheckable(True)
        self.move_act.triggered.connect(lambda: self.toggle_mode('move'))

        self.subtract_background_act = QAction('Background Subtraction', self)
        self.subtract_background_act.setStatusTip('Toggle background subtraction')
        self.subtract_background_act.setCheckable(True)
        self.subtract_background_act.triggered.connect(self.toggle_background_subtraction)

        self.snap_background_act = QAction('&Snap Background', self)
        self.snap_background_act.setStatusTip('Snap background image')
        self.snap_background_act.triggered.connect(self.snap_background)

        self.snap_raw_photo_act = QAction('Snap Raw Photo', self)
        self.snap_raw_photo_act.setStatusTip('Snap a single raw photo')
        self.snap_raw_photo_act.triggered.connect(self.snap_photo)

        self.snap_processed_photo_act = QAction('Snap Photo')
        self.snap_processed_photo_act.setStatusTip('Snap a single background subtracted photo')
        self.snap_processed_photo_act.triggered.connect(self.snap_processed_photo)

        self.laser_sweep_act = QAction('Sweep Laser')
        self.laser_sweep_act.triggered.connect(self.laser_sweep)

        self.z_sweep_act = QAction('Focus Sweep')
        self.z_sweep_act.setStatusTip('Perform a focus sweep')
        self.z_sweep_act.triggered.connect(self.z_sweep)

        self.video_act = QAction(QIcon(application_path + "images/recordstart.png"), "&Capture Video", self)
        self.video_act.setToolTip("Capture Video")
        self.video_act.setCheckable(True)
        self.video_act.toggled.connect(self.toggle_video)

        self.toggle_grid_act = QAction('Grid')
        self.toggle_grid_act.setStatusTip('Toggles whether to use a grid for background')
        self.toggle_grid_act.setCheckable(True)
        self.toggle_grid_act.toggled.connect(lambda value: setattr(self, 'grid', value))


        self.grab_release_laser_act = QAction('Open laser')
        self.grab_release_laser_act.setCheckable(True)
        self.grab_release_laser_act.triggered.connect(self.laser.toggle_laser)



        exit_act = QAction('E&xit', self)
        exit_act.setShortcut(QKeySequence.Quit)
        exit_act.setStatusTip('Exit program')
        exit_act.triggered.connect(self.close)

        #=========#
        # Menubar #
        #=========#

        file_menu = self.menuBar().addMenu('&File')
        file_menu.addAction(exit_act)

        device_menu = self.menuBar().addMenu('&Device')
        device_menu.addAction(self.device_select_act)
        device_menu.addAction(self.device_properties_act)
        device_menu.addAction(self.device_driver_properties_act)
        device_menu.addAction(self.set_roi_act)
        device_menu.addAction(self.move_act)
        device_menu.addAction(self.start_live_act)
        device_menu.addSeparator()
        device_menu.addAction(self.close_device_act)

        capture_menu = self.menuBar().addMenu('&Capture')
        capture_menu.addAction(self.snap_raw_photo_act)
        capture_menu.addSeparator()
        capture_menu.addAction(self.snap_processed_photo_act)
        capture_menu.addAction(self.z_sweep_act)
        capture_menu.addAction(self.snap_background_act)
        capture_menu.addAction(self.subtract_background_act)
        capture_menu.addAction(self.toggle_grid_act)
        



        #=========#
        # Toolbar #
        #=========#

        toolbar = QToolBar(self)
        self.addToolBar(Qt.TopToolBarArea, toolbar)
        toolbar.addAction(self.device_select_act)
        toolbar.addAction(self.device_properties_act)
        toolbar.addAction(self.grab_release_laser_act)
        toolbar.addSeparator()
        toolbar.addAction(self.start_live_act)
        toolbar.addAction(self.video_act)
        toolbar.addSeparator()
        toolbar.addAction(self.set_roi_act)
        toolbar.addAction(self.move_act)
        toolbar.addSeparator()
        toolbar.addAction(self.subtract_background_act)
        toolbar.addAction(self.snap_background_act)
        toolbar.addAction(self.toggle_grid_act)
        toolbar.addSeparator()
        toolbar.addAction(self.snap_raw_photo_act)
        toolbar.addAction(self.snap_processed_photo_act)
        toolbar.addAction(self.laser_sweep_act)
        toolbar.addAction(self.z_sweep_act)
        # button = QPushButton("metadata", toolbar)
        # button.clicked.connect(self.generate_metadata)
        # toolbar.addWidget(button)



        self.setCentralWidget(self.video_view)
        

        self.statusBar().showMessage('Ready')
        self.aquisition_label = QLabel('', self.statusBar())
        self.statusBar().addPermanentWidget(self.aquisition_label)
        self.statistics_label = QLabel('', self.statusBar())
        self.camera.statistics_update.connect(lambda s1, s2: (self.statistics_label.setText(s1), self.statistics_label.setToolTip(s2)))
        self.statusBar().addPermanentWidget(self.statistics_label)
        self.statusBar().addPermanentWidget(QLabel('  '))
        self.camera_label = QLabel(self.statusBar())
        self.statusBar().addPermanentWidget(self.camera_label)
        self.camera.label_update.connect(self.camera_label.setText)
        

        

    def update_controls(self):
        grabber = self.camera.grabber
        if not grabber.is_device_open:
            self.statistics_label.clear()
        
        xy_stage_connected = not not self.xy_stage
        xy_needed = self.grid
        xy_okay = (xy_needed and xy_stage_connected) or not xy_needed

        z_stage_connected = not not self.z_stage

        self.device_properties_act.setEnabled(grabber.is_device_valid and not self.aquiring)
        self.device_driver_properties_act.setEnabled(grabber.is_device_valid and not self.aquiring)
        self.start_live_act.setEnabled(grabber.is_device_valid and not self.aquiring)
        self.start_live_act.setChecked(grabber.is_streaming)
        self.video_act.setEnabled(grabber.is_streaming and not self.aquiring)
        self.close_device_act.setEnabled(grabber.is_device_open and not self.aquiring)
        self.snap_background_act.setEnabled(grabber.is_streaming and not self.aquiring and xy_okay)
        self.snap_processed_photo_act.setEnabled(grabber.is_streaming and not self.aquiring and xy_okay)
        self.snap_raw_photo_act.setEnabled(grabber.is_streaming and not self.aquiring)
        self.z_sweep_act.setEnabled(grabber.is_streaming and not self.aquiring and z_stage_connected and xy_okay and self.laser.open)
        self.set_roi_act.setEnabled(grabber.is_device_valid and not self.video_view.background.rect().isEmpty() and not self.aquiring)
        self.move_act.setEnabled(grabber.is_streaming and not self.aquiring and xy_okay)
        self.move_act.setChecked(self.video_view.mode == 'move')
        self.set_roi_act.setChecked(self.video_view.mode == 'roi')
        self.subtract_background_act.setEnabled(self.background is not None)
        self.laser_sweep_act.setEnabled(self.laser.open and not self.aquiring and grabber.is_streaming)
        self.grab_release_laser_act.setChecked(self.laser.open)

    def closeEvent(self, ev: QCloseEvent):
        self.camera.closeEvent(ev)
    
    #==============================================#
    # Functions to take raw images and aquisitions #
    #==============================================#
    
    # Snap and save one raw image
    def snap_photo(self):
        self.camera.new_frame.connect(self.save_image, Qt.ConnectionType.SingleShotConnection)
    

    def save_image(self, image: np.ndarray):
        dialog = QFileDialog(self, 'Save Photo')
        dialog.setNameFilter('TIFF (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)

        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            tiff.imwrite(filepath + '.tif', image)
        self.data_directory = dialog.directory()



    # Sequence handling

    class AquisitionWorkerThread(QThread):
        done = Signal()
        def __init__(self, parent, func, *args):
            super().__init__(parent)
            self.args = args
            self.photos = []
            self.func = func
            self.parent = parent
            parent.aquiring_mutex.lock()
            parent.aquiring = True
            parent.aquiring_mutex.unlock()
            parent.update_controls()

        def run(self):
            self.func(*self.args)
            self.done.emit()
            self.finish_aquisition()
        
        def finish_aquisition(self):
            self.parent.aquiring_mutex.lock()
            self.parent.aquiring = False
            self.parent.aquiring_mutex.unlock()
            self.parent.update_controls()

    def take_sequence(self):
        distance = 4
        positions = np.array([[0,0], [1,0], [1,1], [0,1]])*distance
        anchor = np.array(self.mmc.getXYPosition(self.xy_stage))
        for i, position in enumerate(positions):
            pos = position + anchor
            self.mmc.setXYPosition(pos[0], pos[1])
            self.mmc.waitForDevice(self.xy_stage)
            time.sleep(0.2)
            # shoot photo and wait for it to be shot
            self.camera.new_frame.connect(self.store_sequence_image, Qt.ConnectionType.SingleShotConnection)
            self.got_image_mutex.lock()
            self.got_image.wait(self.got_image_mutex)
            self.got_image_mutex.unlock()
        
        # Return to base
        self.mmc.setXYPosition(anchor[0], anchor[1])

    def store_sequence_image(self, image: np.ndarray):
        self.photos.append(image)
        self.got_image.wakeAll()
    
    def toggle_video(self, start: bool):
        if start:
            self.start_video()
        else:
            self.stop_video()

    def start_video(self):
        self.photos = []
        self.new_processed_frame.connect(self.write_frame)

    def write_frame(self, frame: np.ndarray):
        self.photos.append(frame)
    
    def stop_video(self):
        self.new_processed_frame.disconnect(self.write_frame)

        dialog = QFileDialog(self, 'Save Video')
        dialog.setNameFilters(('Multi Page TIF (*.tif)', 'AVI Video (*.avi)'))
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.save_videos_directory)
        if dialog.exec():

            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            nameFilter = dialog.selectedNameFilter()
            if '.tif' in nameFilter:
                photos = np.array(self.photos)
                if photos.dtype == np.uint16:
                    photos = (photos/256).astype(np.uint8)
                
                tiff.imwrite(filepath + '.tif', np.array(self.photos))

            elif '.avi' in nameFilter:
                fps = int(self.camera.device_property_map.get_value_float(ic4.PropId.ACQUISITION_FRAME_RATE))
                self.writer = cv2.VideoWriter(filepath + '.avi', cv2.VideoWriter_fourcc(*'XVID'), fps, (self.roi_width, self.roi_height), False)

                for photo in self.photos:
                    # Image writer only support uint8
                    if photo.dtype == np.uint16:
                        self.writer.write((photo/256).astype(np.uint8))
                    elif (photo.dtype ==np.uint8):
                        self.writer.write(photo)

                
                self.writer.release()
        self.save_videos_directory = dialog.directory()



    # Snap a sequence of images in a grid to calculate the background and save it.
    # else snap one image and save it

    def snap_background(self):
        if self.grid:
            self.photos = []
            if not self.aquiring:
                self.aquisition_worker = self.AquisitionWorkerThread(self, self.take_sequence)
                self.aquisition_worker.done.connect(self.set_background)
                self.aquisition_worker.start()
        else:
            self.camera.new_frame.connect(self.set_background, Qt.ConnectionType.SingleShotConnection)
    
    def set_background(self, image: np.ndarray=None):
        if image is not None:
            self.background = image
        else:
            self.background = pc.common_background(self.photos)
        self.update_controls()
    
    # Background subtracted photos

    def snap_processed_photo(self):
        if self.grid:
            self.photos = []
            if not self.aquiring:
                self.aquisition_worker = self.AquisitionWorkerThread(self, self.take_sequence)
                self.aquisition_worker.done.connect(self.save_processed_photo)
                self.aquisition_worker.start()
        else:
            # Snap single picture
            self.new_processed_frame.connect(self.save_image, Qt.ConnectionType.SingleShotConnection)

    def save_processed_photo(self):
        dialog = QFileDialog(self, 'Save Photo')
        dialog.setNameFilter('TIFF (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            
            background = pc.common_background(self.photos)
            data = self.photos[0]

            diff = pc.background_subtracted(data, background)

            
            # also contains raw data
            tiff.imwrite(filepath + '.tif', pc.float_to_mono(diff))
            np.save(os.path.splitext(filepath)[0] + '_raw.npy', self.photos)
        self.data_directory = dialog.directory()

    # Make a laser sweep

    def laser_sweep(self):
        bandwidth = self.laser.bandwith
        band_radius = self.laser.bandwith/2
        dialog = SweepDialog(self, title="Laser Sweep Data", limits=(475+band_radius, 850-bandwidth, 475+bandwidth, 850-band_radius), defaults=(600, 700, 10), unit="nm")
        if dialog.exec() and not self.aquiring:
            self.wavelens = np.linspace(*dialog.get_values())
            self.aquisition_worker = self.AquisitionWorkerThread(self, self.take_laser_sweep)
            self.aquisition_worker.done.connect(self.save_laser_data)
            self.aquisition_worker.start()
            

    def take_laser_sweep(self):
        N = len(self.wavelens)
        self.laser.set_wavelen(self.wavelens[0])
        time.sleep(5)
        self.laser_data_raw = []
        for i, wavelen in enumerate(self.wavelens):
            self.aquisition_label.setText(f'Aquiring Data: laser sweep progression {i+1}/{N}')
            self.laser.set_wavelen(wavelen)
            time.sleep(0.5)
            if self.grid:
                self.photos = []
                self.take_sequence()
                self.laser_data_raw.append(self.photos)
                self.background = pc.common_background(self.photos)
            else:
                self.camera.new_frame.connect(self.store_laser_data, Qt.ConnectionType.SingleShotConnection)
                self.got_image_mutex.lock()
                self.got_image.wait(self.got_image_mutex)
                self.got_image_mutex.unlock()
        
        self.aquisition_label.setText('Calculating Images')
    
    def store_laser_data(self, image: np.ndarray):
        self.laser_data_raw.append(image)
        self.got_image.wakeAll()
    
    def save_laser_data(self):
        dialog = QFileDialog(self, 'Save Wavelength Sweep')
        dialog.setNameFilter('TIFF image sequence (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            
            images = np.array(self.laser_data_raw)

            if np.shape(images)[1] == 4:
                np.save(filepath + '_raw.npy', images)
                diff = np.array([pc.background_subtracted(photos[0], pc.common_background(photos)) for photos in images])
                images = pc.float_to_mono(diff)

            tiff.imwrite(filepath + '.tif', images)

            metadata = self.generate_metadata()
            metadata['Laser.wavelength [nm]'] = {
                "Start": int(self.wavelens[0]),
                "Stop": int(self.wavelens[-1]),
                "Number": len(self.wavelens)}
            with open(filepath+'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()
        self.aquisition_label.setText('')
        self.statusBar().showMessage('Done!')

    # Make a Z sweep

    def z_sweep(self):
        dialog = SweepDialog(self, title="Z Sweep Data", limits=(-10, 10, -10, 10), defaults=(0, 1, 10), unit="micron")
        if dialog.exec() and not self.aquiring:
            self.z_positions = np.linspace(*dialog.get_values())
            self.aquisition_worker = self.AquisitionWorkerThread(self, self.take_z_sweep)
            self.aquisition_worker.done.connect(self.save_z_data)
            self.aquisition_worker.start()
    
    def take_z_sweep(self):
        z_zero = self.mmc.getZPosition()
        N = len(self.z_positions)
        
        self.z_data_raw = []
        for i, z in enumerate(self.z_positions):
            self.aquisition_label.setText(f'Aquiring Data: z sweep progression {i+1}/{N}')

            # Set position
            pos = z_zero + z
            self.z_position = i
            self.mmc.setZPosition(pos)
            self.mmc.waitForDevice(self.z_stage)
            time.sleep(0.1)
            # Take picture
            if self.grid:
                self.photos = []
                self.take_sequence()
                self.z_data_raw.append(self.photos)
                self.background = pc.common_background(self.photos)
            else:
                self.camera.new_frame.connect(self.store_z_data, Qt.ConnectionType.SingleShotConnection)
                self.got_image_mutex.lock()
                self.got_image.wait(self.got_image_mutex)
                self.got_image_mutex.unlock()

        self.mmc.setZPosition(z_zero)
        self.aquisition_label.setText('Calculating Images')
        
    def store_z_data(self, image: np.ndarray):
        self.z_data_raw.append(image)
        self.got_image.wakeAll()
    

    def save_z_data(self):
        dialog = QFileDialog(self, 'Save Z Sweep')
        dialog.setNameFilter('TIFF image sequence (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            
            images = np.array(self.z_data_raw)

            if np.shape(images)[1] == 4:
                np.save(filepath + '_raw.npy', images)
                diff = np.array([pc.background_subtracted(photos[0], pc.common_background(photos)) for photos in images])
                images = pc.float_to_mono(diff)

            tiff.imwrite(filepath + '.tif', images)

            metadata = self.generate_metadata()
            metadata['Setup.z_focus [um]'] = {
                "Start": int(self.z_positions[0]),
                "Stop": int(self.z_positions[-1]),
                "Number": len(self.z_positions)}
            
            with open(filepath +'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()
        self.aquisition_label.setText('')
        self.statusBar().showMessage('Done!')

    
    def init_roi(self, width, height, max_width, max_height, offset_x, offset_y):
        self.roi_width = width
        self.roi_height = height
    
    def update_roi(self, roi):
        # Set ROI in camera
        self.camera.startStopStream()
        self.camera.device_property_map.set_value(ic4.PropId.WIDTH, int(roi.width()))
        self.camera.device_property_map.set_value(ic4.PropId.HEIGHT, int(roi.height()))
        self.camera.device_property_map.set_value(ic4.PropId.OFFSET_X, int(roi.left()))
        self.camera.device_property_map.set_value(ic4.PropId.OFFSET_Y, int(roi.top()))
        self.camera.startStopStream()
        self.roi_width = roi.width()
        self.roi_height = roi.height()
        self.subtract_background = False
        self.background = None

        # Go out of roi mode in UI
        self.update_controls()
    
    def move_stage(self, displacement: np.ndarray):
        displacement_micron = 3.45*displacement/40
        self.mmc.setRelativeXYPosition(-displacement_micron[1], -displacement_micron[0])

    def toggle_background_subtraction(self):
        self.subtract_background = not self.subtract_background
    
    def toggle_mode(self, mode):
        if self.video_view.mode == mode:
            self.video_view.mode = 'navigation'
        else:
            self.video_view.mode = mode
            
        self.update_controls()
        
    
    def update_display(self, frame: np.ndarray):
        if (self.subtract_background and self.background is not None):
            # (reference + signal) / reference
            diff = pc.background_subtracted(frame, self.background)
            frame = pc.float_to_mono(diff)
        self.new_processed_frame.emit(frame)
        self.video_view.update_image(frame)

    
    def generate_metadata(self) -> dict:
        exposure_auto = self.camera.device_property_map.get_value_bool(ic4.PropId.EXPOSURE_AUTO)
        if exposure_auto:
            exposure_time = "auto"
        else:
            exposure_time = int(self.camera.device_property_map.get_value_float(ic4.PropId.EXPOSURE_TIME))
        return({
            "Camera.fps": self.camera.device_property_map.get_value_float(ic4.PropId.ACQUISITION_FRAME_RATE),
            "Camera.exposure_time [us]": exposure_time,
            "Laser.wavelength [nm]": self.laser.wavelen,
            "Laser.bandwith [nm]": self.laser.bandwith,
            "Laser.frequency [kHz]": self.laser.get_frequency()
        })