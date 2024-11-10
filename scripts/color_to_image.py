import sys
from PyQt5.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy, QPushButton, QSpacerItem
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QImage
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from sklearn.cluster import KMeans
import io

class ImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setText("\n\n Drag and Drop an Image Here \n\n")
        self.setStyleSheet("""
            QLabel{
                border: 4px dashed #aaa;
                font-size: 16px;
                color: #555;
            }
        """)
        self.setAcceptDrops(True)  # Enable drag and drop

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            print("Drag Enter Event: Accepted")
        else:
            event.ignore()
            print("Drag Enter Event: Ignored")

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                print(f"Image dropped: {file_path}")
                self.parent().process_image(file_path)
        else:
            event.ignore()
            print("Drop Event: Ignored")

class ColorDisplay(QFrame):
    def __init__(self, color, rgb_code, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 140)  # Increased size for better visibility
        self.setStyleSheet(f"background-color: rgb{color}; border: 1px solid #000;")

        # Layout inside the frame
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Spacer to push the button to the bottom
        spacer = QSpacerItem(20, 100, QSizePolicy.Minimum, QSizePolicy.Expanding)
        layout.addItem(spacer)

        # Create the copy button
        self.button = QPushButton(rgb_code)
        self.button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.8);
                border: none;
                font-size: 10px;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: rgba(200, 200, 200, 0.8);
            }
        """)
        self.button.setFixedSize(110, 25)
        self.button.clicked.connect(self.copy_to_clipboard)

        layout.addWidget(self.button, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    def copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.button.text())
        print(f"Copied to clipboard: {self.button.text()}")
        original_text = self.button.text()
        self.button.setText("Copied!")
        QTimer.singleShot(1000, lambda: self.button.setText(original_text))

class AppDemo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Image Processing with Text and Dominant Colors')
        self.resize(1000, 800)

        main_layout = QVBoxLayout()

        # Image drag and drop area
        self.image_label = ImageLabel(self)
        main_layout.addWidget(self.image_label)

        # Dominant colors and complementary color display
        self.colors_layout = QHBoxLayout()

        # Dominant Colors
        self.dominant_label = QLabel("Dominant Colors:")
        self.dominant_label.setStyleSheet("font-size: 16px;")
        self.colors_layout.addWidget(self.dominant_label)

        self.colors_container = QHBoxLayout()
        self.colors_layout.addLayout(self.colors_container)

        # Complementary Color
        self.complementary_label = QLabel("Text Color:")
        self.complementary_label.setStyleSheet("font-size: 16px; margin-left: 20px;")
        self.colors_layout.addWidget(self.complementary_label)

        self.complementary_color_display = ColorDisplay((255, 255, 255), "RGB(255, 255, 255)")
        self.colors_layout.addWidget(self.complementary_color_display)

        main_layout.addLayout(self.colors_layout)

        # Processed image preview with text
        self.preview_label = QLabel("Preview with Text:")
        self.preview_label.setStyleSheet("font-size: 16px; margin-top: 20px;")
        main_layout.addWidget(self.preview_label)

        self.processed_image_label = QLabel()
        self.processed_image_label.setAlignment(Qt.AlignCenter)
        self.processed_image_label.setStyleSheet("""
            QLabel{
                border: 2px solid #aaa;
            }
        """)
        self.processed_image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.processed_image_label)

        self.setLayout(main_layout)

    def process_image(self, file_path):
        try:
            # Load the image
            image = Image.open(file_path)
            image = image.convert("RGB")
            print("Image loaded successfully!")

            # Convert the image to an array
            image_array = np.array(image)
            pixels = image_array.reshape((-1, 3))

            # Use KMeans to find dominant colors
            kmeans = KMeans(n_clusters=3, random_state=0)
            kmeans.fit(pixels)
            colors = kmeans.cluster_centers_.astype(int)
            print(f"Dominant colors: {colors}")

            # Clear previous colors
            while self.colors_container.count():
                child = self.colors_container.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            # Display dominant colors
            for color in colors:
                color_tuple = tuple(color)
                rgb_code = f"RGB({color[0]}, {color[1]}, {color[2]})"
                color_display = ColorDisplay(color_tuple, rgb_code)
                self.colors_container.addWidget(color_display)
                print(f"Displayed color: {rgb_code}")

            # Choose the first dominant color
            dominant_color = tuple(colors[0])
            print(f"Chosen dominant color: {dominant_color}")

            # Compute the complementary color for the text
            complementary_color = self.get_complementary_color(dominant_color)
            print(f"Complementary color: {complementary_color}")

            # Update the complementary color display
            complementary_rgb_code = f"RGB({complementary_color[0]}, {complementary_color[1]}, {complementary_color[2]})"
            self.complementary_color_display.rgb_code = complementary_rgb_code
            self.complementary_color_display.button.setText(complementary_rgb_code)
            self.complementary_color_display.setStyleSheet(
                f"background-color: rgb{complementary_color}; border: 1px solid #000;"
            )
            print(f"Complementary color updated to: {complementary_rgb_code}")

            # Add text to the image using the complementary color
            image_with_text = image.copy()
            draw = ImageDraw.Draw(image_with_text)

            # Calculate font size dynamically based on image size
            image_width, image_height = image.size
            font_size = max(int(min(image_width, image_height) * 0.05), 20)  # At least 20px
            print(f"Calculated font size: {font_size}")

            try:
                font = ImageFont.truetype("arial.ttf", size=font_size)
                print("Custom font loaded.")
            except IOError:
                font = ImageFont.load_default()
                print("Custom font not found, using default font.")

            text = "HELLO WORLD"

            # Use font.getbbox to calculate text size
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Calculate the position to center the text
            text_x = (image_width - text_width) // 2
            text_y = (image_height - text_height) // 2

            draw.text((text_x, text_y), text, fill=complementary_color, font=font)
            print("Text added to image!")

            # Convert the processed image to a format PyQt can display
            qt_image = self.pil_to_qt(image_with_text)
            self.processed_image_label.setPixmap(qt_image)
            self.processed_image_label.setText("")
            print("Image displayed successfully!")

        except Exception as e:
            print(f"Error processing image: {e}")
            self.image_label.setText(f"Error processing image:\n{e}")

    def pil_to_qt(self, pil_image):
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        qt_image = QImage()
        qt_image.loadFromData(buffer.getvalue(), "PNG")
        pixmap = QPixmap.fromImage(qt_image)
        scaled_pixmap = pixmap.scaled(
            self.processed_image_label.width(),
            self.processed_image_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        return scaled_pixmap

    def get_complementary_color(self, rgb_color):
        return tuple(255 - component for component in rgb_color)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    demo = AppDemo()
    demo.show()
    sys.exit(app.exec_())
