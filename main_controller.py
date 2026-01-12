from PySide6.QtCore import QObject, Signal, QThread, QMutex, QWaitCondition, Qt, QSettings, QStandardPaths, QTimer
from PySide6.QtWidgets import QFileDialog

import time
import numpy as np
from numpy.typing import NDArray

import os
import tifffile as tiff
import cv2
import yaml

from pathlib import Path
from datetime import datetime
import shutil

import logging

import processing as pc

from controllers import StageController, PumpController, LaserController, CameraController
from widgets import PropertiesDialog

class PersistentWorkerThread(QThread):
    def __init__(self, func):
        super().__init__()
        self.func = func


class acquisitionWorkerThread(QThread):
        done = Signal()
        def __init__(self, parent, func, *args):
            super().__init__(parent)
            self.args = args
            self.photos = []
            self.func = func
            self.parent = parent
            
            parent.cancel_acquisition.connect(self.terminate)

        def run(self):
            self.func(*self.args)
            self.done.emit()


class MainController(QObject):
    update_controls = Signal()
    update_background = Signal(np.ndarray)
    cancel_acquisition = Signal()
    def __init__(self, ):
        super().__init__()

        # Setup devices
        self.stage = StageController()
        self.pump = PumpController(self)
        self.laser = LaserController(self)
        self.camera = CameraController(self)
        self.camera.new_frame.connect(self.set_exposure)

        # 99th percentile of exposure
        self.exposure = 0
        # Routes
        self.pump.changedState.connect(self.update_controls)
        self.laser.changedState.connect(self.update_controls)


        self.shot_count = 10 # Shoot 10 images to average over

        # Storage for acquisition parameters
        self.media: list = []
        self.z_positions: NDArray = np.array([])
        self.wavelens: NDArray = np.array([])

        self.got_image_mutex = QMutex()
        self.got_image = QWaitCondition()

        self.acquiring = False
        self.acquiring_mutex = QMutex()

        # Load settings
        self.settings = QSettings('Casper', 'Monitor')

        self.data_directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)


        if self.settings.contains('magnification') and self.settings.contains('pxsize'):
            self.magnification = self.settings.value('magnification', type=int)
            self.pxsize = self.settings.value('pxsize', type=float)
        else:
            self.magnification = 60 # Default
            self.pxsize = 3.45
            self.settings = QSettings('Casper', 'Monitor')
            self.set_setup_parameters()

    def set_setup_parameters(self):
        dialog = PropertiesDialog(self.magnification, self.pxsize)
        if dialog.exec():
            self.magnification, self.pxsize = dialog.get_values()
            self.settings.setValue('magnification', self.magnification)
            self.settings.setValue('pxsize', self.pxsize)
    
    def cleanup(self):
        self.camera.cleanup()
        self.pump.cleanup()
        self.laser.cleanup()

    # =====================================================
    # =================   Actions   =======================
    # =====================================================


    def take_z_sweep(self, actions):
        """Move to different defocus then perform next action"""
        z_zero = self.stage.get_z_position()
        for i, z in enumerate(self.z_positions*10/1.4):
            # Set position
            pos = z_zero + z
            self.z_position = i
            self.stage.set_z_position(pos)
            time.sleep(1)
            # Next action
            self.action(actions)

        # Reset
        self.stage.set_z_position(z_zero)


    def take_laser_sweep(self, actions):
        """Move to different wavelen then perform next action"""
        init_wavelen = self.laser.wavelen
        self.laser.set_wavelen(self.wavelens[0])
        time.sleep(2)
        self.laser_data_raw = []
        for i, wavelen in enumerate(self.wavelens):
            self.laser.set_wavelen(wavelen)
            time.sleep(0.2)
            # Auto exposure
            self.auto_expose()
            time.sleep(0.2)
            # Take next action
            self.action(actions)
        
        # Reset laser
        self.laser.set_wavelen(init_wavelen)
    

    def take_media_sweep(self, actions):
        """Move to medium and then perform next action"""

        input = self.media

        self.pump.wait_till_ready()
        for medium in input:
            self.pump.pickup(medium, 60)
            self.pump.wait_till_ready()
            self.pump.dispense(self.pump.flowcell, 60)
            self.pump.wait_till_ready()

            # Auto adjust exposure
            self.auto_expose()
            self.action(actions)
            self.store_medium_data()
    
    def take_media_sweep_const_exposure(self, actions):
        """Move to medium and then perform next action"""

        input = self.media

        self.pump.wait_till_ready()
        for medium in input:
            self.pump.pickup(medium, 60)
            self.pump.wait_till_ready()
            self.pump.dispense(self.pump.flowcell, 60)
            self.pump.wait_till_ready()

            # Auto adjust exposure
            self.action(actions)

    def store_medium_data(self):
        data = np.squeeze(self.photos)
        shape = np.shape(data)
        images = data.reshape(*self.shape, self.shot_count+3, *shape[1:])
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
        filepath = Path(folder) / datetime.now().strftime("%Y%m%d_%H%M%S.npy")
        np.save(filepath, images)
        self.photos = []
        self.temp_files.append(filepath)

    # Image taking

    def take_single(self):
        """Take a single photo and store it"""
        self.camera.new_frame.connect(self.store_image, Qt.ConnectionType.SingleShotConnection)
        self.got_image_mutex.lock()
        # Retry
        while not self.got_image.wait(self.got_image_mutex, 1000):
            self.camera.new_frame.connect(self.store_image, Qt.ConnectionType.SingleShotConnection)
        self.got_image_mutex.unlock()

    def take_single_avg(self):
        """Take a single averaged photo and store it"""
        for i in range(self.shot_count):
            self.take_single()


    def take_sequence(self):
        """Take a grid photo and store it"""
        distance = 4
        positions = np.array([[1,0], [1,1], [0,1]])*distance
        anchor = np.array(self.stage.get_xy_position())

        self.take_single()
            
        for i, position in enumerate(positions):
            pos = position + anchor
            self.stage.set_xy_position(pos)
            time.sleep(0.2)
            self.take_single()
        
        # Return to base
        self.stage.set_xy_position(anchor)

    def take_sequence_avg(self):
        """Take a grid photo and store it"""
        distance = 4
        positions = np.array([[1,0], [1,1], [0,1]])*distance
        anchor = np.array(self.stage.get_xy_position())

        self.take_single_avg()
            
        for i, position in enumerate(positions):
            pos = position + anchor
            self.stage.set_xy_position(pos)
            time.sleep(0.2)
            self.take_single()
        
        # Return to base
        self.stage.set_xy_position(anchor)

    
    
    def store_image(self, image: np.ndarray):
        self.photos.append(image)
        self.got_image.wakeAll()
    

    # =====================================================
    # ===============   acquisitions   =====================
    # =====================================================
    
    def action(self, actions):
        """Define action chains"""
        if len(actions) == 1:
            # Final action
            return actions[0]()
        else:
            return actions[0](actions[1:])
    

    def start_acquisition(self, finish, *actions):
        actionsfunc = lambda: self.action(actions)
        # Clear photo buffer
        self.photos = []
        self.acquisition_worker = acquisitionWorkerThread(self, actionsfunc)
        self.acquisition_worker.done.connect(finish)
        self.acquisition_worker.done.connect(self.finish_acquisition)

        self.acquiring_mutex.lock()
        self.acquiring = True
        self.acquiring_mutex.unlock()
        self.update_controls.emit()

        self.acquisition_worker.start()

    def finish_acquisition(self):
        logging.debug('Finished acquisition')
        self.cancel_acquisition.emit()
        self.acquiring_mutex.lock()
        self.acquiring = False
        self.acquiring_mutex.unlock()
        self.media = []
        self.update_controls.emit()
    

    # =====================================================
    # =======   Complete measurement protocols   ==========
    # =====================================================

    def acquire(self, params: dict):
        logging.debug(f'starting acquisition with {params}')
        """Accepts and parses requests"""
        self.shape = []
        self.temp_files = []
        actions = []
        if 'media' in params.keys():
            if not self.pump.open:
                raise RuntimeError('Pump is not open, cannot sweep media')
            self.media = params['media']
            actions.append(self.take_media_sweep)
        if 'defocus' in params.keys():
            if self.stage.z_stage is None:
                raise RuntimeError('Z stage is not open, cannot sweep defocus')
            self.shape.append(params['defocus'][2])
            self.z_positions = np.linspace(*params['defocus'])
            actions.append(self.take_z_sweep)
        if 'wavelen' in params.keys():
            if not self.laser.open:
                raise RuntimeError('Laser is not open, cannot sweep media')
            
            start, stop, num = params['wavelen']
            self.shape.append(num)

            # Sweep from long to short bc laser is more powerful with long
            # This helps with auto exposure bc overexposure is unlikely this way
            self.wavelens = np.linspace(start, stop, num)
            actions.append(self.take_laser_sweep)
        
        
        actions.append(self.take_sequence_avg)
        

        self.start_acquisition(self.finish_sweeps, *actions)
    
    def finish_sweeps(self):
        dialog = QFileDialog(caption='Save Acquisition')
        dialog.setNameFilter('Raw Data (*.npy)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            
            if len(self.temp_files) > 0:
                # Saved in files
                for i, file in enumerate(self.temp_files):
                    shutil.move(file, f'{filepath}_{i}.npy')
            else:
                data = np.squeeze(self.photos)
                shape = np.shape(data)
                images = data.reshape(*self.shape, self.shot_count+3, *shape[1:])
                np.save(filepath + '.npy', images)
                if len(self.shape) == 1:
                    tiff.imwrite(filepath + '.tif', images[:,0])

            metadata = self.generate_metadata()
            with open(filepath+'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()
        self.wavelens = np.array([])
        self.z_positions = np.array([])


    # Snap and save one raw image
    def snap_photo(self):
        self.camera.new_frame.connect(self.save_image, Qt.ConnectionType.SingleShotConnection)
    

    def save_image(self, image: np.ndarray):
        dialog = QFileDialog(caption='Save Photo')
        dialog.setNameFilter('TIFF (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)

        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            tiff.imwrite(filepath + '.tif', image)
        self.data_directory = dialog.directory()
    
    
    
    # Background subtracted photos

    def snap_processed_photo(self):
        self.start_acquisition(self.save_processed_photo, self.take_sequence_avg)

    def save_processed_photo(self):
        dialog = QFileDialog(caption='Save Photo')
        dialog.setNameFilter('TIFF (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            
            background = pc.common_background(self.photos[-4:])
            data = np.mean(self.photos[:-3], axis=0)
            diff = pc.background_subtracted(data, background)
            
            # also contains raw data
            tiff.imwrite(filepath + '.tif', pc.float_to_mono(diff))
            np.save(os.path.splitext(filepath)[0] + '.npy', self.photos)

            metadata = self.generate_metadata()
            with open(filepath+'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()
    
    def media_sweep(self, media):
        self.media = media
        self.start_acquisition(self.save_medium_data, self.take_media_sweep_const_exposure, self.take_sequence_avg)

    def save_medium_data(self):
        dialog = QFileDialog(caption='Save Medium Sweep')
        dialog.setNameFilter('TIFF image sequence (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            
            data = np.squeeze(self.photos)
            shape = np.shape(data)
            images = data.reshape(len(self.media), self.shot_count+3, *shape[1:])
            np.save(filepath + '.npy', images)
            tiff.imwrite(filepath + '.tif', images[:,0])

            metadata = self.generate_metadata()
            with open(filepath+'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()
        self.media = np.array([])


    def laser_sweep(self, start, stop, num):
        self.wavelens = np.linspace(start, stop, num)
        self.start_acquisition(self.save_laser_data, self.take_laser_sweep, self.take_sequence_avg)
    
    def save_laser_data(self):
        dialog = QFileDialog(caption='Save Wavelength Sweep')
        dialog.setNameFilter('TIFF image sequence (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]
            
            data = np.squeeze(self.photos)
            shape = np.shape(data)
            images = data.reshape(len(self.wavelens), self.shot_count+3, *shape[1:])
            np.save(filepath + '.npy', images)
            tiff.imwrite(filepath + '.tif', images[:,0])

            metadata = self.generate_metadata()
            with open(filepath+'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()
        self.wavelens = np.array([])
    

    def z_sweep(self, start, stop, num):
        self.z_positions = np.linspace(start, stop, num)
        self.start_acquisition(self.save_z_data, self.take_z_sweep, self.take_sequence_avg)
    
    def save_z_data(self):
        dialog = QFileDialog(caption='Save Z Sweep')
        dialog.setNameFilter('TIFF image sequence (*.tif)')
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)
        if dialog.exec():
            filepath = dialog.selectedFiles()[0]
            filepath = os.path.splitext(filepath)[0]

            data = np.squeeze(self.photos)
            shape = np.shape(data)
            images = data.reshape(len(self.z_positions), self.shot_count+3, *shape[1:])
            np.save(filepath + '.npy', images)
            tiff.imwrite(filepath + '.tif', images[:,0])

            metadata = self.generate_metadata()
            
            with open(filepath +'.yaml', 'w') as file:
                yaml.dump(metadata, file)
        self.data_directory = dialog.directory()
        self.z_positions = np.array([])

    def generate_metadata(self) -> dict:
        exposure_auto = self.camera.get_exposure_auto()
        if exposure_auto:
            exposure_time = 'auto'
        else:
            exposure_time = self.camera.get_exposure_time()
        
        if len(self.wavelens) > 0:
            exposure_time = 'auto'
            wavelen = {
                'Start': int(self.wavelens[0]),
                'Stop': int(self.wavelens[-1]),
                'Number': len(self.wavelens)}
        else:
            wavelen = self.laser.wavelen
        
        if len(self.z_positions) > 0:
            z_position = {
                'Start': float(self.z_positions[0]),
                'Stop': float(self.z_positions[-1]),
                'Number': len(self.z_positions)}
        else:
            z_position = 0
            
        
        return {
            'Camera.fps': self.camera.get_fps(),
            'Camera.exposure_time [us]': exposure_time,
            'Camera.pixel_size [um]': self.pxsize,
            'Camera.averaging': self.shot_count,
            'Setup.magnification': self.magnification,
            'Setup.defocus [um]': z_position,
            'Laser.wavelength [nm]': wavelen,
            'Laser.bandwith [nm]': self.laser.bandwith,
            'Laser.frequency [kHz]': self.laser.get_frequency()
        }
    
    # =====================================================
    # =================   Video   =========================
    # =====================================================
    
    def toggle_video(self, start: bool):
        if start:
            self.start_video()
        else:
            self.stop_video()

    def start_video(self):
        self.photos = []
        self.camera.new_frame.connect(self.write_frame)

    def write_frame(self, frame: np.ndarray):
        self.photos.append(frame)
    
    def stop_video(self):
        self.camera.new_frame.disconnect(self.write_frame)

        dialog = QFileDialog(caption='Save Video')
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
                fps = int(self.camera.get_fps())
                self.writer = cv2.VideoWriter(filepath + '.avi', cv2.VideoWriter_fourcc(*'XVID'), fps, (self.camera.roi_width, self.camera.roi_height), False)  # type: ignore

                for photo in self.photos:
                    # Image writer only support uint8
                    if photo.dtype == np.uint16:
                        self.writer.write((photo/256).astype(np.uint8))
                    elif (photo.dtype ==np.uint8):
                        self.writer.write(photo)

                
                self.writer.release()
        self.save_videos_directory = dialog.directory()
    
    def update_roi(self, roi):
        # Set ROI in camera
        self.camera.set_roi(roi)

    def set_exposure(self, frame: np.ndarray):
        self.exposure = np.max(frame)
    
    def auto_expose(self):
        if self.exposure > 55000:
            self.camera.set_autoexposure('Continuous')
            time.sleep(2)
            self.camera.set_autoexposure('Off')
        
        self.camera.set_exposure(self.camera.get_exposure()*50000/self.exposure)

    def end_auto_expose(self):
        self.camera.set_autoexposure('Off')
        self.camera.set_exposure(self.camera.get_exposure()*50000/self.exposure)

    def auto_expose_non_blocking(self):
        if self.exposure > 55000:
            self.camera.set_autoexposure('Continuous')
            QTimer.singleShot(int(2*1000), self.end_auto_expose)
        else:
            self.camera.set_exposure(self.camera.get_exposure()*50000/self.exposure)
            
    