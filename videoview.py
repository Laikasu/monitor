from PySide6.QtCore import QRect, QMargins, Qt, QPoint, Signal
from PySide6.QtGui import QPixmap, QImage, QPen, QBrush
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem

import numpy as np

import imagingcontrol4 as ic4

class VideoView(QGraphicsView):
    roi_set = Signal(QRect)
    move_stage = Signal(np.ndarray)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        
        self.camera_display = QGraphicsPixmapItem()
        self._scene.addItem(self.camera_display)

        self.background = QGraphicsRectItem()
        self.background.setZValue(-1)
        self.background.setBrush(QBrush(Qt.black))
        self._scene.addItem(self.background)

        self.roi_graphic = QGraphicsRectItem()
        self.roi_graphic.setZValue(1)
        self.roi_graphic.setPen(QPen(Qt.red, 2))
        self._scene.addItem(self.roi_graphic)

        self.setMinimumSize(640, 480)
        self.setScene(self._scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self.zoom_factor = 1.25
        self.current_scale = 1.0
        self.start_point = None

        self._mode = "navigation"
    
    @property
    def mode(self) -> str:
        return self._mode
    
    @mode.setter
    def mode(self, new_mode: str):
        if (new_mode == "navigation" or new_mode =="move"):
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        elif (new_mode == "roi"):
            self.setDragMode(QGraphicsView.NoDrag)
        else:
            raise ValueError(f"Unexpected input: mode {new_mode} unknown")
        self._mode = new_mode

        

    
    def set_size(self, width, height, offset_x, offset_y):
        self.width = width
        self.height = height
        self.background.setRect(QRect(0, 0, width, height))
        self.camera_display.setOffset(QPoint(offset_x, offset_y))
        self.centerOn(self.background.boundingRect().center())
        self.scale(0.25,0.25)
        self.current_scale *= 0.25
        

    def update_image(self, frame):
        height, width, channels = np.shape(frame)
            
        if frame.dtype == np.uint16:
            self.camera_display.setPixmap(QPixmap.fromImage(QImage(frame.data, width, height, 2*channels*width, QImage.Format_Grayscale16)))
        elif frame.dtype == np.uint8:
            self.camera_display.setPixmap(QPixmap.fromImage(QImage(frame.data, width, height, channels*width, QImage.Format_Grayscale8)))

        

    def wheelEvent(self, event):
        """
        Override the wheelEvent to zoom in or out.
        """
        # if event.modifiers() & Qt.ControlModifier:  # Check if Ctrl is held
        if event.angleDelta().y() > 0:  # Scroll up to zoom in
            self.zoom_in()
        else:  # Scroll down to zoom out
            self.zoom_out()
        # else:
        #     # Pass the event to the parent class for default behavior (e.g., scrolling)
        #super().wheelEvent(event)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_margins()

    def zoom_in(self):
        """
        Zoom in by scaling up.
        """
        self.scale(self.zoom_factor, self.zoom_factor)
        self.current_scale *= self.zoom_factor
        self.update_margins()

    def zoom_out(self):
        """
        Zoom out by scaling down.
        """
        self.scale(1 / self.zoom_factor, 1 / self.zoom_factor)
        self.current_scale /= self.zoom_factor
        self.update_margins()
    
    def reset_zoom(self):
        """
        Reset zoom to the original scale.
        """
        self.resetTransform()
        self.update_margins()
        self.current_scale = 1.0
    
    def get_bounds(self):
        bounds = np.array(self.mapToScene(self.viewport().rect()).boundingRect().getCoords(), dtype=np.int16)
        bounds[0] = max(bounds[0], 0)
        bounds[1] = max(bounds[1], 0)
        bounds[2] = min(bounds[2], self.camera_display.pixmap().width() - 1)
        bounds[3] = min(bounds[3], self.camera_display.pixmap().height() - 1)
        return bounds
    
    def update_margins(self):
        """
        Make margins of half the viewport size around the camera to enable panning up to the borders
        """
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        size = rect.size()
        w = size.width() // 2
        h = size.height() // 2
        m = QMargins(w, h, w, h)
        rect = self.background.rect().marginsAdded(m).toRect()
        self.setSceneRect(rect)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.mode == "move":
                self.start_point = self.mapToScene(event.pos())
            if self.mode == "roi":
                # Start drawing a new rectangle
                self.start_point = self.mapToScene(event.pos()).toPoint()
                self.start_point.setX(np.round(np.clip(self.start_point.x(), 0, self.width)/16)*16)
                self.start_point.setY(np.round(np.clip(self.start_point.y(), 0, self.height)/16)*16)
                self.roi_graphic.show()
            if self.mode == "navigation":
                super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.start_point is not None:
            if self.mode == "move":
                current_point = self.mapToScene(event.pos())
                displacement = current_point - self.start_point
                self.start_point = current_point
                self.move_stage.emit(np.array(displacement.toTuple()))

            if self.mode == "roi":
                # Update the graphic
                end_point = self.mapToScene(event.pos()).toPoint()
                end_point.setX(np.round(np.clip(end_point.x(), 0, self.width)/16)*16)
                end_point.setY(np.round(np.clip(end_point.y(), 0, self.height)/16)*16)
                rect = QRect(self.start_point, end_point).normalized()
                self.roi_graphic.setRect(rect)
        return super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.start_point is not None:
                if self.mode == "move":
                    self.start_point = None
                if self.mode == "roi":
                    # Update the graphic
                    end_point = self.mapToScene(event.pos()).toPoint()
                    end_point.setX(np.round(np.clip(end_point.x(), 0, self.width)/16)*16 - 1)
                    end_point.setY(np.round(np.clip(end_point.y(), 0, self.height)/16)*16 - 1)
                    rect = QRect(self.start_point, end_point).normalized()
                    self.roi_graphic.setRect(rect)
                    # Update roi and turn off roi mode
                    self.mode = "navigation"
                    self.start_point = None  # Reset start point
                    self.roi_set.emit(rect)
                    self.roi_graphic.hide()
                    self.camera_display.setOffset(rect.topLeft())
        return super().mouseReleaseEvent(event)


