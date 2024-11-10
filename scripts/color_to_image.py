import sys
from PyQt5.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy
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
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                print(f"Image dropped: {file_path}")  # לוג להורדת תמונה
                self.parent().process_image(file_path)
        else:
            event.ignore()

class ColorDisplay(QFrame):
    def __init__(self, color, rgb_code, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 50)
        self.setStyleSheet(f"background-color: rgb{color}; border: 1px solid #000;")
        self.rgb_code = rgb_code

        # יצירת לייבל לקוד RGB
        self.label = QLabel(self.rgb_code, self)
        self.label.setStyleSheet("color: #000; font-size: 10px; background-color: rgba(255, 255, 255, 0.7);")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setGeometry(0, 50, 50, 20)  # מיקום מתחת לצבע

        # התחברות לאירוע לחיצה להעתקה ללוח
        self.label.mousePressEvent = self.copy_to_clipboard

    def copy_to_clipboard(self, event):
        print(f"Attempting to copy: {self.rgb_code}")  # לוג לנסיון העתקה
        clipboard = QApplication.clipboard()
        clipboard.setText(self.rgb_code)
        print("Copied to clipboard!")  # לוג להצלחה בהעתקה
        self.label.setText("Copied!")  # עדכון טקסט זמני
        QTimer.singleShot(1000, lambda: self.label.setText(self.rgb_code))  # חזרה לטקסט המקורי אחרי 1 שנייה

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
        self.colors_label = QLabel("Dominant Colors:")
        self.colors_label.setStyleSheet("font-size: 16px;")
        self.colors_layout.addWidget(self.colors_label)

        self.colors_container = QHBoxLayout()
        self.colors_layout.addLayout(self.colors_container)

        # Display for the complementary text color
        self.complementary_label = QLabel("Text Color:")
        self.complementary_label.setStyleSheet("font-size: 16px; margin-left: 20px;")
        self.colors_layout.addWidget(self.complementary_label)

        self.complementary_color_display = QLabel()
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
            print("Image loaded successfully!")  # לוג להצלחה בטעינת תמונה

            # Convert the image to an array
            image_array = np.array(image)
            pixels = image_array.reshape((-1, 3))

            # Use KMeans to find dominant colors
            kmeans = KMeans(n_clusters=3, random_state=0)
            kmeans.fit(pixels)
            colors = kmeans.cluster_centers_.astype(int)
            print(f"Dominant colors: {colors}")  # לוג לצבעים דומיננטיים

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

            # Choose the first dominant color
            dominant_color = tuple(colors[0])
            print(f"Chosen dominant color: {dominant_color}")  # לוג לבחירת צבע דומיננטי

            # Compute the complementary color for the text
            complementary_color = self.get_complementary_color(dominant_color)
            self.complementary_color_display.setText(f"RGB: {complementary_color}")
            self.complementary_color_display.setStyleSheet(
                f"background-color: rgb{complementary_color}; border: 1px solid #000;"
            )
            print(f"Complementary color: {complementary_color}")  # לוג לצבע משלים

            # Add text to the image using the complementary color
            image_with_text = image.copy()
            draw = ImageDraw.Draw(image_with_text)

            # Calculate font size dynamically based on image size
            image_width, image_height = image.size
            font_size = int(min(image_width, image_height) * 0.1)  # 10% of the smaller dimension
            print(f"Calculated font size: {font_size}")  # לוג לגודל הגופן

            try:
                font = ImageFont.truetype("arial.ttf", size=font_size)
            except IOError:
                font = ImageFont.load_default()

            text = "HELLO WORLD"

            # Use font.getbbox to calculate text size
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Calculate the position to center the text
            text_x = (image_width - text_width) // 2
            text_y = (image_height - text_height) // 2

            draw.text((text_x, text_y), text, fill=complementary_color, font=font)
            print("Text added to image!")  # לוג להוספת טקסט לתמונה

            # Convert the processed image to a format PyQt can display
            qt_image = self.pil_to_qt(image_with_text)
            self.processed_image_label.setPixmap(qt_image)
            self.processed_image_label.setText("")
            print("Image displayed successfully!")  # לוג להצלחה בהצגת תמונה

        except Exception as e:
            print(f"Error processing image: {e}")  # לוג לשגיאה
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
