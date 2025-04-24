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
        self.setText("\n\n גרור והפיל תמונה כאן \n\n")
        self.setStyleSheet("""
            QLabel{
                border: 4px dashed #aaa;
                font-size: 16px;
                color: #555;
            }
        """)
        self.setAcceptDrops(True)  # הפעלת קבלת גרירה

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            print("אירוע גרירה התקבל")
        else:
            event.ignore()
            print("אירוע גרירה נדחה")

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                print(f"ניסיון לפתוח את הקובץ: {file_path}")
                self.parent().process_image(file_path)
        else:
            event.ignore()
            print("אירוע הפלה נדחה")

class ColorDisplay(QFrame):
    def __init__(self, color, rgb_code, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 140)  # הגדלת הגודל לנראות טובה יותר
        self.setStyleSheet(f"background-color: rgb{color}; border: 1px solid #000;")

        # עימוד פנימי בתוך ה-QFrame
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Spacer לדחיפת הכפתור לתחתית
        spacer = QSpacerItem(20, 100, QSizePolicy.Minimum, QSizePolicy.Expanding)
        layout.addItem(spacer)

        # יצירת כפתור ההעתקה
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
        print(f"הועתק ללוח: {self.button.text()}")
        original_text = self.button.text()
        self.button.setText("הועתק!")
        QTimer.singleShot(1000, lambda: self.button.setText(original_text))

class AppDemo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('עיבוד תמונה עם טקסט וצבעים דומיננטיים')
        self.resize(1000, 800)

        main_layout = QVBoxLayout()

        # אזור לגרירת תמונה
        self.image_label = ImageLabel(self)
        main_layout.addWidget(self.image_label)

        # אזור להצגת הצבעים הדומיננטיים והצבע המשלים
        self.colors_layout = QHBoxLayout()

        # הצבעים הדומיננטיים
        self.dominant_label = QLabel("צבעים דומיננטיים:")
        self.dominant_label.setStyleSheet("font-size: 16px;")
        self.colors_layout.addWidget(self.dominant_label)

        self.colors_container = QHBoxLayout()
        self.colors_layout.addLayout(self.colors_container)

        # הצבע המשלים
        self.complementary_label = QLabel("צבע הטקסט המשלים:")
        self.complementary_label.setStyleSheet("font-size: 16px; margin-left: 20px;")
        self.colors_layout.addWidget(self.complementary_label)

        self.complementary_color_display = ColorDisplay((255, 255, 255), "RGB(255, 255, 255)")
        self.colors_layout.addWidget(self.complementary_color_display)

        main_layout.addLayout(self.colors_layout)

        # תצוגת התמונה המעובדת עם הטקסט
        self.preview_label = QLabel("תצוגה מקדימה עם טקסט:")
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
            # טען את התמונה
            image = Image.open(file_path)
            image = image.convert("RGB")
            print("תמונה נטענת בהצלחה!")

            # המר את התמונה למערך
            image_array = np.array(image)
            pixels = image_array.reshape((-1, 3))

            # השתמש ב-KMeans כדי למצוא צבעים דומיננטיים
            kmeans = KMeans(n_clusters=3, random_state=0)
            kmeans.fit(pixels)
            colors = kmeans.cluster_centers_.astype(int)
            print(f"צבעים דומיננטיים: {colors}")

            # נקה את הצבעים הקודמים
            while self.colors_container.count():
                child = self.colors_container.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            # הצג את הצבעים הדומיננטיים
            for color in colors:
                color_tuple = tuple(color)
                rgb_code = f"RGB({color[0]}, {color[1]}, {color[2]})"
                color_display = ColorDisplay(color_tuple, rgb_code)
                self.colors_container.addWidget(color_display)
                print(f"צבע מוצג: {rgb_code}")

            # בחר את הצבע הדומיננטי הראשון
            dominant_color = tuple(colors[0])
            print(f"צבע דומיננטי נבחר: {dominant_color}")

            # חשב את הצבע המשלים לטקסט
            complementary_color = self.get_complementary_color(dominant_color)
            print(f"צבע משלים לטקסט: {complementary_color}")

            # עדכן את הצבע המשלים בממשק
            complementary_rgb_code = f"RGB({complementary_color[0]}, {complementary_color[1]}, {complementary_color[2]})"
            self.complementary_color_display.rgb_code = complementary_rgb_code
            self.complementary_color_display.button.setText(complementary_rgb_code)
            self.complementary_color_display.setStyleSheet(
                f"background-color: rgb{complementary_color}; border: 1px solid #000;"
            )
            print(f"צבע משלים עודכן ל: {complementary_rgb_code}")

            # הוסף טקסט לתמונה עם הצבע המשלים
            image_with_text = image.copy()
            draw = ImageDraw.Draw(image_with_text)

            # חשב את גודל הגופן באופן דינמי לפי גודל התמונה
            image_width, image_height = image.size
            font_size = max(int(min(image_width, image_height) * 0.1), 30)  # 10% מהמדד הקטן יותר, לפחות 30
            print(f"גודל גופן מחושב: {font_size}")

            try:
                font = ImageFont.truetype("arial.ttf", size=font_size)
                print("גופן מותאם אישית נטען.")
            except IOError:
                font = ImageFont.load_default()
                print("גופן מותאם אישית לא נמצא, שימוש בגופן ברירת מחדל.")

            text = "HELLO WORLD"

            # השתמש ב-font.getbbox כדי לחשב את גודל הטקסט
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # חשב את המיקום למרכז הטקסט
            text_x = (image_width - text_width) // 2
            text_y = (image_height - text_height) // 2

            draw.text((text_x, text_y), text, fill=complementary_color, font=font)
            print("טקסט נוסף לתמונה!")

            # המר את התמונה המעובדת לפורמט PyQt להצגה
            qt_image = self.pil_to_qt(image_with_text)
            self.processed_image_label.setPixmap(qt_image)
            self.processed_image_label.setText("")
            print("תמונה מוצגת בהצלחה!")

        except Exception as e:
            print(f"שגיאה בעיבוד התמונה: {e}")
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
