
from threading import Lock

from PySide6.QtCore import QStandardPaths, QDir, QTimer, QEvent, QFileInfo, Qt
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QMainWindow, QMessageBox, QLabel, QApplication, QFileDialog, QToolBar, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
import os
from datetime import datetime
import cv2
import numpy as np
import ctypes

import imagingcontrol4 as ic4

GOT_PHOTO_EVENT = QEvent.Type(QEvent.Type.User + 1)
DEVICE_LOST_EVENT = QEvent.Type(QEvent.Type.User + 2)

class ZoomableGraphicsView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom_factor = 1.25  # Zoom in/out factor
        self.current_scale = 1.0  # Track the current scale

    def wheelEvent(self, event):
        """
        Override the wheelEvent to zoom in or out.
        """
        if event.modifiers() & Qt.ControlModifier:  # Check if Ctrl is held
            if event.angleDelta().y() > 0:  # Scroll up to zoom in
                self.zoom_in()
            else:  # Scroll down to zoom out
                self.zoom_out()
        else:
            # Pass the event to the parent class for default behavior (e.g., scrolling)
            super().wheelEvent(event)

    def zoom_in(self):
        """
        Zoom in by scaling up.
        """
        self.scale(self.zoom_factor, self.zoom_factor)
        self.current_scale *= self.zoom_factor

    def zoom_out(self):
        """
        Zoom out by scaling down.
        """
        self.scale(1 / self.zoom_factor, 1 / self.zoom_factor)
        self.current_scale /= self.zoom_factor

    def reset_zoom(self):
        """
        Reset zoom to the original scale.
        """
        self.resetTransform()
        self.current_scale = 1.0

class GotPhotoEvent(QEvent):
    def __init__(self, buffer: ic4.ImageBuffer):
        QEvent.__init__(self, GOT_PHOTO_EVENT)
        self.image_buffer = buffer

class MainWindow(QMainWindow):
    def __init__(self):
        application_path = os.path.abspath(os.path.dirname(__file__)) + os.sep
        QMainWindow.__init__(self)
        self.setWindowIcon(QIcon(application_path + "/images/tis.ico"))

        # Make sure the %appdata%/demoapp directory exists
        appdata_directory = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        picture_directory = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        video_directory = QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)
        QDir(appdata_directory).mkpath(".")
        

        self.data_directory = picture_directory + "/Data"
        QDir(self.data_directory).mkpath(".")
        self.backgrounds_directory = picture_directory + "/Backgrounds"
        QDir(self.backgrounds_directory).mkpath(".")
        self.save_videos_directory = video_directory

        self.device_file = appdata_directory + "/device.json"
        self.codec_config_file = appdata_directory + "/codecconfig.json"

        self.shoot_photo_mutex = Lock()
        self.shoot_photo = False
        self.shoot_bg = False

        self.capture_to_video = False
        self.video_capture_pause = False

        self.grabber = ic4.Grabber()
        self.grabber.event_add_device_lost(lambda g: QApplication.postEvent(self, QEvent(DEVICE_LOST_EVENT)))

        self.processing_mutex = Lock()
        self.background = None
        self.subtract_background = False

        class Listener(ic4.QueueSinkListener):
            def sink_connected(self, sink: ic4.QueueSink, image_type: ic4.ImageType, min_buffers_required: int) -> bool:
                # Allocate more buffers than suggested, because we temporarily take some buffers
                # out of circulation when saving an image or video files.
                sink.alloc_and_queue_buffers(min_buffers_required + 2)
                return True

            def sink_disconnected(self, sink: ic4.QueueSink):
                pass

            def frames_queued(listener, sink: ic4.QueueSink):
<<<<<<< HEAD
                buf = sink.pop_output_buffer()
                buffer_wrap = buf.numpy_copy()
=======
                with self.processing_mutex:
                    buf = sink.pop_output_buffer()
                    buffer_wrap = buf.numpy_wrap()
>>>>>>> c2a1aedee50168fa0c4a1c814ef44a9e6aa796c0

                    with self.shoot_photo_mutex:
                        if self.shoot_photo:
                            self.shoot_photo = False

                            # Send an event to the main thread with a reference to 
                            # the main thread of our GUI. 
                            QApplication.postEvent(self, GotPhotoEvent(buf))

                    if self.capture_to_video and not self.video_capture_pause:
                        try:
                            self.video_writer.add_frame(buf)
                        except ic4.IC4Exception as ex:
                            pass
                    
                    if (self.subtract_background):
                        if (self.background is not None):
                            cv2.subtract(buffer_wrap, self.background, buffer_wrap)
                            #diff = np.subtract(buffer_wrap, self.background, dtype=np.int16)
                            #dpos = np.where(diff>10, diff.astype(np.uint8), 0)
                            #dneg = np.where(diff<-10, (-diff).astype(np.uint8), 0)
                            #np.add(dneg, dpos, buffer_wrap)
                            #np.copyto(buffer_wrap, self.background)

<<<<<<< HEAD
                # Connect the buffer's chunk data to the device's property map
                # This allows for properties backed by chunk data to be updated
                self.device_property_map.connect_chunkdata(buf)
                height, width, channels = np.shape(buffer_wrap)
                image = QImage(buffer_wrap.data, width, height, channels*width, QImage.Format_Grayscale8)
                self.video.setPixmap(QPixmap.fromImage(image))
=======
                            #buffer_wrap[np.abs(diff)>10] = 0
                    
                        
                        #np.copyto(buffer_wrap[:,:,0], dpos, where=(dpos != 0))
                        #np.copyto(buffer_wrap[:,:,2], dneg, where=(dneg != 0))
                        
                        #cv2.subtract(buffer_wrap, self.background, buffer_wrap)

                    # Connect the buffer's chunk data to the device's property map
                    # This allows for properties backed by chunk data to be updated
                    self.device_property_map.connect_chunkdata(buf)
                    self.display.display_buffer(buf)
>>>>>>> c2a1aedee50168fa0c4a1c814ef44a9e6aa796c0
        

        self.sink = ic4.QueueSink(Listener())

        self.property_dialog = None

        self.video_writer = ic4.VideoWriter(ic4.VideoWriterType.MP4_H264)

        self.createUI()

        # try:
        #     self.display = self.video_widget.as_display()
        #     self.display.set_render_position(ic4.DisplayRenderPosition.STRETCH_CENTER)
        # except Exception as e:
        #     QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)

        if QFileInfo.exists(self.device_file):
            try:
                self.grabber.device_open_from_state_file(self.device_file)
                self.onDeviceOpened()
            except ic4.IC4Exception as e:
                QMessageBox.information(self, "", f"Loading last used device failed: {e}", QMessageBox.StandardButton.Ok)

        if QFileInfo.exists(self.codec_config_file):
            try:
                self.video_writer.property_map.deserialize_from_file(self.codec_config_file)
            except ic4.IC4Exception as e:
                QMessageBox.information(self, "", f"Loading last codec configuration failed: {e}", QMessageBox.StandardButton.Ok)

        self.updateControls()
    
    

    def createUI(self):
        self.resize(1024, 768)

        #=========#
        # Actions #
        #=========#
        application_path = os.path.abspath(os.path.dirname(__file__)) + os.sep
        
        self.device_select_act = QAction(QIcon(application_path + "images/camera.png"), "&Select", self)
        self.device_select_act.setStatusTip("Select a video capture device")
        self.device_select_act.setShortcut(QKeySequence.Open)
        self.device_select_act.triggered.connect(self.onSelectDevice)

        self.device_properties_act = QAction(QIcon(application_path + "images/imgset.png"), "&Properties", self)
        self.device_properties_act.setStatusTip("Show device property dialog")
        self.device_properties_act.triggered.connect(self.onDeviceProperties)

        self.device_driver_properties_act = QAction("&Driver Properties", self)
        self.device_driver_properties_act.setStatusTip("Show device driver property dialog")
        self.device_driver_properties_act.triggered.connect(self.onDeviceDriverProperties)

        self.trigger_mode_act = QAction(QIcon(application_path + "images/triggermode.png"), "&Trigger Mode", self)
        self.trigger_mode_act.setStatusTip("Enable and disable trigger mode")
        self.trigger_mode_act.setCheckable(True)
        self.trigger_mode_act.triggered.connect(self.onToggleTriggerMode)

        self.start_live_act = QAction(QIcon(application_path + "images/livestream.png"), "&Live Stream", self)
        self.start_live_act.setStatusTip("Start and stop the live stream")
        self.start_live_act.setCheckable(True)
        self.start_live_act.triggered.connect(self.startStopStream)

        self.shoot_photo_act = QAction(QIcon(application_path + "images/photo.png"), "&Shoot Photo", self)
        self.shoot_photo_act.setStatusTip("Shoot and save a photo")
        self.shoot_photo_act.triggered.connect(self.onShootPhoto)

        self.record_start_act = QAction(QIcon(application_path + "images/recordstart.png"), "&Capture Video", self)
        self.record_start_act.setToolTip("Capture video into MP4 file")
        self.record_start_act.setCheckable(True)
        self.record_start_act.triggered.connect(self.onStartStopCaptureVideo)

        self.record_pause_act = QAction(QIcon(application_path + "images/recordpause.png"), "&Pause Capture Video", self)
        self.record_pause_act.setStatusTip("Pause video capture")
        self.record_pause_act.setCheckable(True)
        self.record_pause_act.triggered.connect(self.onPauseCaptureVideo)

        self.record_stop_act = QAction(QIcon(application_path + "images/recordstop.png"), "&Stop Capture Video", self)
        self.record_stop_act.setStatusTip("Stop video capture")
        self.record_stop_act.triggered.connect(self.onStopCaptureVideo)

        self.codec_property_act = QAction(QIcon(application_path + "images/gear.png"), "&Codec Properties", self)
        self.codec_property_act.setStatusTip("Configure the video codec")
        self.codec_property_act.triggered.connect(self.onCodecProperties)

        self.close_device_act = QAction("Close", self)
        self.close_device_act.setStatusTip("Close the currently opened device")
        self.close_device_act.setShortcuts(QKeySequence.Close)
        self.close_device_act.triggered.connect(self.onCloseDevice)

        self.select_background_act = QAction("Select &Backgrounds", self)
        self.select_background_act.setStatusTip("Select background images")
        self.select_background_act.triggered.connect(self.select_background)

        self.save_background_act = QAction("&Save Background", self)
        self.save_background_act.setStatusTip("Save background image")
        self.save_background_act.triggered.connect(self.onShootBG)

        self.background_subtraction_act = QAction("Background Subtraction", self)
        self.background_subtraction_act.setStatusTip("Toggle background subtraction")
        self.background_subtraction_act.setCheckable(True)
        self.background_subtraction_act.triggered.connect(self.toggle_background_subtraction)



        exit_act = QAction("E&xit", self)
        exit_act.setShortcut(QKeySequence.Quit)
        exit_act.setStatusTip("Exit program")
        exit_act.triggered.connect(self.close)

        #=========#
        # Menubar #
        #=========#

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(exit_act)

        device_menu = self.menuBar().addMenu("&Device")
        device_menu.addAction(self.device_select_act)
        device_menu.addAction(self.device_properties_act)
        device_menu.addAction(self.device_driver_properties_act)
        device_menu.addAction(self.trigger_mode_act)
        device_menu.addAction(self.start_live_act)
        device_menu.addSeparator()
        device_menu.addAction(self.close_device_act)

        capture_menu = self.menuBar().addMenu("&Capture")
        capture_menu.addAction(self.shoot_photo_act)
        capture_menu.addAction(self.record_start_act)
        capture_menu.addAction(self.record_pause_act)
        capture_menu.addAction(self.record_stop_act)
        capture_menu.addAction(self.codec_property_act)
        capture_menu.addAction(self.select_background_act)
        capture_menu.addAction(self.save_background_act)
        capture_menu.addAction(self.background_subtraction_act)


        #=========#
        # Toolbar #
        #=========#

        toolbar = QToolBar(self)
        self.addToolBar(Qt.TopToolBarArea, toolbar)
        toolbar.addAction(self.device_select_act)
        toolbar.addAction(self.device_properties_act)
        toolbar.addSeparator()
        toolbar.addAction(self.trigger_mode_act)
        toolbar.addSeparator()
        toolbar.addAction(self.start_live_act)
        toolbar.addSeparator()
        toolbar.addAction(self.shoot_photo_act)
        toolbar.addSeparator()
        toolbar.addAction(self.record_start_act)
        toolbar.addAction(self.record_pause_act)
        toolbar.addAction(self.record_stop_act)
        toolbar.addAction(self.codec_property_act)
        toolbar.addAction(self.save_background_act)
        toolbar.addAction(self.select_background_act)
        toolbar.addAction(self.background_subtraction_act)

        # self.video_widget = ic4.pyside6.DisplayWidget()
        # self.video_widget.setMinimumSize(640, 480)
        self.video_scene = QGraphicsScene(self)
        self.video_view = ZoomableGraphicsView(self)
        self.video_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.video_view.setScene(self.video_scene)
        #self.video_view.setAlignment(Qt.AlignCenter)
        self.video_view.setMinimumSize(640, 480)

        self.setCentralWidget(self.video_view)
        self.video = QGraphicsPixmapItem()
        self.video_scene.addItem(self.video)
        

        self.statusBar().showMessage("Ready")
        self.statistics_label = QLabel("", self.statusBar())
        self.statusBar().addPermanentWidget(self.statistics_label)
        self.statusBar().addPermanentWidget(QLabel("  "))
        self.camera_label = QLabel(self.statusBar())
        self.statusBar().addPermanentWidget(self.camera_label)

        self.update_statistics_timer = QTimer()
        self.update_statistics_timer.timeout.connect(self.onUpdateStatisticsTimer)
        self.update_statistics_timer.start()
        

    def onCloseDevice(self):
        if self.grabber.is_streaming:
            self.startStopStream()
        
        try:
            self.grabber.device_close()
        except:
            pass

        self.device_property_map = None
        self.display.display_buffer(None)

        self.updateControls()

    def closeEvent(self, ev: QCloseEvent):
        if self.grabber.is_streaming:
            self.grabber.stream_stop()

        if self.grabber.is_device_valid:
            self.grabber.device_save_state_to_file(self.device_file)
    
    def customEvent(self, ev: QEvent):
        if ev.type() == DEVICE_LOST_EVENT:
            self.onDeviceLost()
        elif ev.type() == GOT_PHOTO_EVENT:
            if (self.shoot_bg):
                self.save_background(ev.image_buffer)
                self.shoot_bg = False
            else:
                self.savePhoto(ev.image_buffer)
            

    def onSelectDevice(self):
        dlg = ic4.pyside6.DeviceSelectionDialog(self.grabber, parent=self)
        if dlg.exec() == 1:
            if not self.property_dialog is None:
                self.property_dialog.update_grabber(self.grabber)
            
            self.onDeviceOpened()
        self.updateControls()

    def onDeviceProperties(self):
        if self.property_dialog is None:
            self.property_dialog = ic4.pyside6.PropertyDialog(self.grabber, parent=self, title="Device Properties")
            # set default vis
        
        self.property_dialog.show()

    def onDeviceDriverProperties(self):
        dlg = ic4.pyside6.PropertyDialog(self.grabber.driver_property_map, parent=self, title="Device Driver Properties")
        # set default vis

        dlg.exec()

        self.updateControls()

    def onToggleTriggerMode(self):
        try:
            self.device_property_map.set_value(ic4.PropId.TRIGGER_MODE, self.trigger_mode_act.isChecked())
        except ic4.IC4Exception as e:
            QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)

    def onShootPhoto(self):
        with self.shoot_photo_mutex:
            self.shoot_photo = True
    
    def onShootBG(self):
        with self.shoot_photo_mutex:
            self.shoot_photo = True
            self.shoot_bg = True

    def onUpdateStatisticsTimer(self):
        if not self.grabber.is_device_valid:
            return
        
        try:
            stats = self.grabber.stream_statistics
            text = f"Frames Delivered: {stats.sink_delivered} Dropped: {stats.device_transmission_error}/{stats.device_underrun}/{stats.transform_underrun}/{stats.sink_underrun}"
            self.statistics_label.setText(text)
            tooltip = (
                f"Frames Delivered: {stats.sink_delivered}"
                f"Frames Dropped:"
                f"  Device Transmission Error: {stats.device_transmission_error}"
                f"  Device Underrun: {stats.device_underrun}"
                f"  Transform Underrun: {stats.transform_underrun}"
                f"  Sink Underrun: {stats.sink_underrun}"
            )
            self.statistics_label.setToolTip(tooltip)
        except ic4.IC4Exception:
            pass

    def onDeviceLost(self):
        QMessageBox.warning(self, "", f"The video capture device is lost!", QMessageBox.StandardButton.Ok)

        # stop video

        self.updateCameraLabel()
        self.updateControls()

    def onDeviceOpened(self):
        self.device_property_map = self.grabber.device_property_map

        trigger_mode = self.device_property_map.find(ic4.PropId.TRIGGER_MODE)
        trigger_mode.event_add_notification(self.updateTriggerControl)

        self.updateCameraLabel()

        # if start_stream_on_open
        self.startStopStream()

    def updateTriggerControl(self, p: ic4.Property):
        if not self.grabber.is_device_valid:
            self.trigger_mode_act.setChecked(False)
            self.trigger_mode_act.setEnabled(False)
        else:
            try:
                self.trigger_mode_act.setChecked(self.device_property_map.get_value_str(ic4.PropId.TRIGGER_MODE) == "On")
                self.trigger_mode_act.setEnabled(True)
            except ic4.IC4Exception:
                self.trigger_mode_act.setChecked(False)
                self.trigger_mode_act.setEnabled(False)

    def updateControls(self):
        if not self.grabber.is_device_open:
            self.statistics_label.clear()

        self.device_properties_act.setEnabled(self.grabber.is_device_valid)
        self.device_driver_properties_act.setEnabled(self.grabber.is_device_valid)
        self.start_live_act.setEnabled(self.grabber.is_device_valid)
        self.start_live_act.setChecked(self.grabber.is_streaming)
        self.shoot_photo_act.setEnabled(self.grabber.is_streaming)
        self.record_stop_act.setEnabled(self.capture_to_video)
        self.record_pause_act.setChecked(self.video_capture_pause)
        self.record_start_act.setChecked(self.capture_to_video)
        self.close_device_act.setEnabled(self.grabber.is_device_open)
        self.save_background_act.setEnabled(self.grabber.is_streaming)

        self.updateTriggerControl(None)

    def updateCameraLabel(self):
        try:
            info = self.grabber.device_info
            self.camera_label.setText(f"{info.model_name} {info.serial}")
        except ic4.IC4Exception:
            self.camera_label.setText("No Device")

    def onPauseCaptureVideo(self):
        self.video_capture_pause = self.record_pause_act.isChecked()

    def onStartStopCaptureVideo(self):
        if self.capture_to_video:
            self.stopCapturevideo()
            return
        
        filters = [
            "MP4 Video Files (*.mp4)"
        ]
        
        dialog = QFileDialog(self, "Capture Video")
        dialog.setNameFilters(filters)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.save_videos_directory)

        if dialog.exec():
            full_path = dialog.selectedFiles()[0]
            self.save_videos_directory = QFileInfo(full_path).absolutePath()

            fps = float(25)
            try:
                fps = self.device_property_map.get_value_float(ic4.PropId.ACQUISITION_FRAME_RATE)
            except:
                pass

            try:
                self.video_writer.begin_file(full_path, self.sink.output_image_type, fps)
            except ic4.IC4Exception as e:
                QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)

            self.capture_to_video = True
            
        self.updateControls()

    def onStopCaptureVideo(self):
        self.capture_to_video = False
        self.video_writer.finish_file()
        self.updateControls()

    def onCodecProperties(self):
        dlg = ic4.pyside6.PropertyDialog(self.video_writer.property_map, self, "Codec Settings")
        # set default vis
        if dlg.exec() == 1:
            self.video_writer.property_map.serialize_to_file(self.codec_config_file)

    def startStopStream(self):
        try:
            if self.grabber.is_device_valid:
                if self.grabber.is_streaming:
                    self.grabber.stream_stop()
                    if self.capture_to_video:
                        self.onStopCaptureVideo()
                else:
                    self.grabber.stream_setup(self.sink)

        except ic4.IC4Exception as e:
            QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)

        self.updateControls()

    def savePhoto(self, image_buffer: ic4.ImageBuffer):
        filters = [
            "Bitmap(*.bmp)",
            "JPEG (*.jpg)",
            "Portable Network Graphics (*.png)",
            "TIFF (*.tif)"
        ]
        
        dialog = QFileDialog(self, "Save Photo")
        dialog.setNameFilters(filters)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDirectory(self.data_directory)

        if dialog.exec():
            selected_filter = dialog.selectedNameFilter()

            full_path = dialog.selectedFiles()[0]
            self.data_directory = QFileInfo(full_path).absolutePath()

            try:
                if selected_filter == filters[0]:
                    image_buffer.save_as_bmp(full_path)
                elif selected_filter == filters[1]:
                    image_buffer.save_as_jpeg(full_path)
                elif selected_filter == filters[2]:
                    image_buffer.save_as_png(full_path)
                else:
                    image_buffer.save_as_tiff(full_path)
            except ic4.IC4Exception as e:
                QMessageBox.critical(self, "", f"{e}", QMessageBox.StandardButton.Ok)
    
    def difference_weighted_average(self, backgrounds):
        # Averaging algorithm
        output_weights = np.zeros_like(backgrounds, dtype=np.float64)
        for i in range(len(backgrounds)):
            for j in range(len(backgrounds)):
                if (i < j):
                    diff = np.abs(np.subtract(backgrounds[i], backgrounds[j], dtype=np.int16))
                    weight = 0.01 + np.where(diff < 10, 1, 0) + np.where(diff < 20, 0.5, 0)
                    output_weights[i] += weight
                    output_weights[j] += weight
                    # plt.imshow(weight, cmap='gray')
                    # plt.show()

        return output_weights
    
    def select_background(self):
        filters = [
            "Bitmap(*.bmp)",
            "JPEG (*.jpg)",
            "Portable Network Graphics (*.png)",
            "TIFF (*.tif)"
        ]
        
        dialog = QFileDialog(self, "Select Backgrounds")
        dialog.setNameFilters(filters)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setDirectory(self.backgrounds_directory)

        if dialog.exec():
            #selected_filter = dialog.selectedNameFilter()
            #full_path = dialog.selectedFiles()[0]
            backgrounds = [cv2.imread(image, 0) for image in dialog.selectedFiles()]

            # Averaging algorithm
            if (len(backgrounds) > 1):
                weights = self.difference_weighted_average(backgrounds)
                background = np.average(backgrounds, axis=0, weights=weights)
            elif (len(backgrounds) == 0):
                background = backgrounds[0]
            else:
                return 0
            self.background = background.astype(backgrounds[0].dtype)[:,:,np.newaxis]
            height, width, channels = np.shape(self.background)
            image = QImage(self.background.data, width, height, channels*width, QImage.Format_Grayscale8)
            self.video.setPixmap(QPixmap.fromImage(image))

            #self.backgrounds_directory = QFileInfo(full_path).absolutePath()

    def save_background(self, image_buffer: ic4.ImageBuffer):
        name = datetime.now().strftime("background_%m-%d_%H-%M-%S")
        image_buffer.save_as_bmp(self.backgrounds_directory + os.sep + f"{name}.bmp")

    def toggle_background_subtraction(self):
        self.subtract_background = not self.subtract_background
        self.background_subtraction_act.setChecked(self.subtract_background)
