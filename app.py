import sys
import os
import json
import base64
import math
import requests
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QComboBox, QPushButton, QFileDialog,
    QScrollArea, QMessageBox, QDialog, QLineEdit, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QSizePolicy, QStackedWidget,
    QGridLayout, QSpacerItem, QMenu, QAction, QStyledItemDelegate, QStyle, QListView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QPoint, QRect, QTimer, QMimeData
from PyQt5.QtGui import QPixmap, QImage, QFont, QColor, QIcon, QPainter, QLinearGradient, QBrush, QPen, QPainterPath


class PlainPasteTextEdit(QTextEdit):
    """与 QTextEdit 一致，但粘贴时丢弃富文本格式，统一用当前编辑器字体显示。
    避免从浏览器/Word 复制带格式的文字粘进来后字体跟手动输入不一致。"""
    def insertFromMimeData(self, source):
        if source.hasText():
            md = QMimeData()
            md.setText(source.text())
            super().insertFromMimeData(md)
        else:
            super().insertFromMimeData(source)


API_URL = "https://www.hfsyapi.cn/v1/images/generations"
API_EDIT_URL = "https://www.hfsyapi.cn/v1/images/edits"
VIDEO_API_URL = "https://www.hfsyapi.cn/v1/video/create"
FILE_UPLOAD_URL = "https://www.hfsyapi.cn/v1/files/image-upload"

RATIO_LIST = ["1:1", "5:4", "9:16", "16:9", "4:3", "3:2", "4:5", "3:4", "2:3", "21:9"]

SIZE_MAP = {
    "1:1":  {"1k": "1024x1024", "2k": "2048x2048", "4k": "2880x2880"},
    "5:4":  {"1k": "1040x832",  "2k": "2080x1664", "4k": "3200x2560"},
    "9:16": {"1k": "720x1280",  "2k": "1152x2048", "4k": "2160x3840"},
    "16:9": {"1k": "1280x720",  "2k": "2048x1152", "4k": "3840x2160"},
    "4:3":  {"1k": "1024x768",  "2k": "2048x1536", "4k": "3264x2448"},
    "3:2":  {"1k": "1008x672",  "2k": "2016x1344", "4k": "3504x2336"},
    "4:5":  {"1k": "832x1040",  "2k": "1664x2080", "4k": "2560x3200"},
    "3:4":  {"1k": "768x1024",  "2k": "1536x2048", "4k": "2448x3264"},
    "2:3":  {"1k": "672x1008",  "2k": "1344x2016", "4k": "2336x3504"},
    "21:9": {"1k": "1344x576",  "2k": "2016x864",  "4k": "3696x1584"},
}

MODEL_QUALITY = {
    "gpt-image-2": ["1k"],
    "gpt-image-2pro": ["2k", "4k"],
}

QUALITY_TO_API = {"1k": "low", "2k": "medium", "4k": "high"}

VIDEO_SIZES = {"横屏": "landscape", "竖屏": "portrait"}
VIDEO_DURATIONS = ["4", "8", "12"]


# 注意：下拉项的灰色高光改用纯 QSS 实现（见 DARK_STYLE 中
# QComboBox QAbstractItemView::item:selected/hover），不再用自定义 delegate。
# 之前 delegate 在 QSS item:selected 样式优先级下不生效，改 QSS 直接控制更稳。
# 给所有 QComboBox 强制使用 QListView 作为下拉视图（默认是 native popup，
# 部分平台 ::item:selected/hover 不会生效）。

_orig_combo_init = QComboBox.__init__

def _patched_combo_init(self, *args, **kwargs):
    _orig_combo_init(self, *args, **kwargs)
    try:
        view = QListView(self)
        view.setMouseTracking(True)
        view.setSelectionMode(QListView.SingleSelection)
        self.setView(view)
        try:
            container = view.window()
            if container is not None:
                container.setStyleSheet("background-color: #000000; border: none;")
                container.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
    except Exception:
        pass

QComboBox.__init__ = _patched_combo_init

DARK_STYLE = """
QWidget {
    font-family: "Segoe UI", "Microsoft YaHei";
    font-size: 14px;
    color: #e0e8f0;
}
QFrame#titleBar {
    background-color: rgba(2, 6, 20, 230);
    border-bottom: 1px solid rgba(125, 211, 252, 0.1);
}
QLabel#titleBrand {
    color: #7dd3fc;
    font-size: 18px;
    font-weight: 700;
    font-style: italic;
}
QLabel#titleSub {
    color: #64748b;
    font-size: 13px;
}
QPushButton#winBtn {
    background: transparent;
    border: none;
    color: #7dd3fc;
    font-size: 16px;
    padding: 6px 12px;
}
QPushButton#winBtn:hover {
    background-color: rgba(125, 211, 252, 0.1);
}
QPushButton#winBtnClose {
    background: transparent;
    border: none;
    color: #7dd3fc;
    font-size: 16px;
    padding: 6px 12px;
}
QPushButton#winBtnClose:hover {
    background-color: rgba(255, 107, 107, 0.2);
    color: #ff6b6b;
}
QFrame#sideNav {
    background-color: rgba(5, 10, 25, 230);
    border-right: 1px solid rgba(255, 255, 255, 0.1);
}
QLabel#navTitle {
    color: #7dd3fc;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 3px;
}
QLabel#navVersion {
    color: #64748b;
    font-size: 11px;
    font-family: "Consolas", "Courier New";
}
QPushButton#navBtn {
    background: transparent;
    border: none;
    border-right: 2px solid transparent;
    color: #94a3b8;
    font-size: 14px;
    font-weight: 500;
    text-align: left;
    padding: 12px 18px;
}
QPushButton#navBtn:hover {
    background-color: rgba(255, 255, 255, 0.05);
    color: #e0f2fe;
}
QPushButton#navBtnActive {
    background-color: rgba(125, 211, 252, 0.12);
    border: none;
    border-right: 2px solid #7dd3fc;
    color: #bae6fd;
    font-size: 14px;
    font-weight: 500;
    text-align: left;
    padding: 12px 18px;
}
QLabel#navKeyLabel {
    color: #64748b;
    font-size: 12px;
    font-family: "Consolas", "Courier New";
}
QFrame#glassPanel {
    background-color: rgba(15, 21, 36, 153);
    border: 1px solid rgba(125, 211, 252, 0.1);
    border-radius: 12px;
}
QLabel#sectionLabel {
    color: #e0e8f0;
    font-size: 15px;
    font-weight: 600;
}
QLabel#sectionBadge {
    color: #64748b;
    font-size: 11px;
    font-family: "Consolas", "Courier New";
    background-color: rgba(30, 41, 59, 0.5);
    padding: 2px 6px;
    border-radius: 3px;
}
QLabel#paramLabel {
    color: #94a3b8;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 2px;
}
QTextEdit#promptInput {
    background-color: rgba(15, 23, 42, 0.4);
    border: 1px solid rgba(125, 211, 252, 0.1);
    border-radius: 8px;
    padding: 12px;
    font-size: 14px;
    color: #a0b4c4;
    selection-background-color: rgba(125, 211, 252, 0.3);
}
QTextEdit#promptInput:focus {
    border: 1px solid rgba(125, 211, 252, 0.4);
}
QComboBox {
    background-color: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(125, 211, 252, 0.1);
    border-radius: 8px;
    padding: 10px 14px;
    font-family: "Inter", "Source Han Sans SC", "思源黑体", "Microsoft YaHei";
    font-size: 15px;
    color: #a0b4c4;
    min-width: 100px;
    min-height: 22px;
}
QComboBox:hover {
    border-color: rgba(125, 211, 252, 0.3);
}
QComboBox:focus {
    border-color: rgba(125, 211, 252, 0.4);
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #64748b;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #000000;
    border: none;
    border-radius: 10px;
    selection-background-color: #4a4a4a;
    selection-color: #ffffff;
    color: #cbd5e1;
    padding: 6px;
    outline: none;
    font-family: "Inter", "Source Han Sans SC", "思源黑体", "Microsoft YaHei";
    font-size: 14px;
}
QComboBox QListView {
    background-color: #000000;
    border: none;
    outline: none;
}
QComboBox QFrame {
    border: none;
    background-color: #000000;
}
QComboBox QAbstractItemView::item {
    background-color: #000000;
    color: #cbd5e1;
    padding: 8px 14px;
    min-height: 28px;
    border: none;
}
QComboBox QAbstractItemView::item:selected {
    background-color: #4a4a4a;
    color: #ffffff;
}
QComboBox QAbstractItemView::item:hover {
    background-color: #4a4a4a;
    color: #ffffff;
}
QPushButton#generateBtn {
    background-color: rgba(125, 211, 252, 0.15);
    border: 1px solid rgba(125, 211, 252, 0.3);
    border-radius: 12px;
    color: #7dd3fc;
    font-size: 18px;
    font-weight: 800;
    padding: 16px;
}
QPushButton#generateBtn:hover {
    background-color: rgba(125, 211, 252, 0.25);
}
QPushButton#generateBtn:pressed {
    background-color: rgba(125, 211, 252, 0.35);
}
QPushButton#generateBtn:disabled {
    background-color: rgba(30, 41, 59, 0.5);
    border-color: rgba(100, 116, 139, 0.2);
    color: #475569;
}
QPushButton#saveBtn {
    background-color: rgba(125, 211, 252, 0.1);
    border: 1px solid rgba(125, 211, 252, 0.2);
    border-radius: 8px;
    color: #7dd3fc;
    font-size: 15px;
    font-weight: 600;
    padding: 10px 24px;
}
QPushButton#saveBtn:hover {
    background-color: rgba(125, 211, 252, 0.2);
}
QPushButton#saveBtn:disabled {
    background-color: rgba(30, 41, 59, 0.3);
    border-color: rgba(100, 116, 139, 0.1);
    color: #334155;
}
QFrame#previewArea {
    background-color: rgba(15, 21, 36, 0.75);
    border: 2px dashed rgba(125, 211, 252, 0.2);
    border-radius: 16px;
}
QLabel#previewPlaceholder {
    color: #475569;
    font-size: 15px;
}
QLabel#previewTitle {
    color: #e0e8f0;
    font-size: 18px;
    font-weight: 700;
}
QLabel#previewDesc {
    color: #94a3b8;
    font-size: 14px;
}
QFrame#footerBar {
    background-color: rgba(15, 21, 36, 0.6);
    border-top: 1px solid rgba(125, 211, 252, 0.1);
}
QLabel#footerText {
    color: #64748b;
    font-size: 11px;
    font-family: "Consolas", "Courier New";
}
QLabel#footerBrand {
    color: rgba(125, 211, 252, 0.4);
    font-size: 11px;
    font-weight: 700;
    font-family: "Consolas", "Courier New";
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: rgba(15, 21, 36, 0.3);
    width: 6px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: rgba(125, 211, 252, 0.2);
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(125, 211, 252, 0.35);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    height: 0px;
}
QLineEdit#refUrlInput {
    background-color: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(125, 211, 252, 0.1);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 14px;
    color: #a0b4c4;
}
QLineEdit#refUrlInput:focus {
    border: 1px solid rgba(125, 211, 252, 0.4);
}
QPushButton#refBtn {
    background-color: rgba(125, 211, 252, 0.1);
    border: 1px solid rgba(125, 211, 252, 0.15);
    border-radius: 8px;
    color: #7dd3fc;
    font-size: 14px;
    font-weight: 600;
    padding: 9px 18px;
}
QPushButton#refBtn:hover {
    background-color: rgba(125, 211, 252, 0.2);
}
QLabel#thumbLabel {
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 4px;
    background-color: rgba(15, 21, 36, 0.4);
}
QLabel#thumbLabel:hover {
    border-color: rgba(125, 211, 252, 0.3);
    background-color: rgba(125, 211, 252, 0.05);
}
QFrame#videoThumb {
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 8px;
    background-color: rgba(15, 21, 36, 0.4);
}
QFrame#videoThumb:hover {
    border-color: rgba(125, 211, 252, 0.3);
    background-color: rgba(125, 211, 252, 0.05);
}
"""

LOGIN_STYLE = """
QDialog {
    background-color: #0a0e1a;
}
QFrame#loginCard {
    background-color: rgba(15, 21, 36, 0.8);
    border: 1px solid rgba(125, 211, 252, 0.1);
    border-radius: 16px;
}
QLabel#loginTitle {
    color: #7dd3fc;
    font-size: 24px;
    font-weight: 700;
    font-style: italic;
}
QLabel#loginSubtitle {
    color: #64748b;
    font-size: 14px;
}
QLabel#loginVersion {
    color: rgba(125, 211, 252, 0.55);
    font-size: 12px;
    font-weight: 700;
    font-family: "Consolas", "Courier New";
    letter-spacing: 1px;
}
QLabel#loginHint {
    color: #94a3b8;
    font-size: 14px;
}
QLineEdit#keyInput {
    background-color: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(125, 211, 252, 0.1);
    border-radius: 8px;
    padding: 11px 14px;
    font-size: 15px;
    color: #a0b4c4;
}
QLineEdit#keyInput:focus {
    border: 1px solid rgba(125, 211, 252, 0.4);
}
QPushButton#loginBtn {
    background-color: rgba(125, 211, 252, 0.15);
    border: 1px solid rgba(125, 211, 252, 0.3);
    color: #7dd3fc;
    border-radius: 8px;
    font-size: 16px;
    font-weight: 700;
    padding: 13px;
}
QPushButton#loginBtn:hover {
    background-color: rgba(125, 211, 252, 0.25);
}
QPushButton#loginBtn:pressed {
    background-color: rgba(125, 211, 252, 0.35);
}
QPushButton#toggleBtn {
    border: none;
    color: #7dd3fc;
    font-size: 14px;
    background: transparent;
}
QPushButton#tutorialBtn {
    border: none;
    color: #64748b;
    font-size: 14px;
    background: transparent;
}
QPushButton#tutorialBtn:hover {
    color: #7dd3fc;
}
"""


def get_logo_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'logo.png')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.png')


def setup_combo(combo):
    combo.setMaxVisibleItems(20)
    combo.view().setMouseTracking(True)



class TutorialDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("如何获取 API Key")
        self.setFixedSize(520, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog { background-color: #0a0e1a; }
            QLabel { color: #e0e8f0; }
            QPushButton#closeBtn {
                background-color: rgba(125, 211, 252, 0.15);
                border: 1px solid rgba(125, 211, 252, 0.3);
                color: #7dd3fc; border-radius: 8px;
                font-size: 13px; font-weight: 600; padding: 10px 28px;
            }
            QPushButton#closeBtn:hover { background-color: rgba(125, 211, 252, 0.25); }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)

        title = QLabel("如何获取 API Key")
        title.setStyleSheet("color: #7dd3fc; font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QLabel()
        content.setWordWrap(True)
        content.setTextFormat(Qt.RichText)
        content.setAlignment(Qt.AlignTop)
        content.setStyleSheet("background: transparent; font-size: 13px; line-height: 1.6; padding: 4px;")
        content.setOpenExternalLinks(True)
        content.setText(
            '<p style="color:#94a3b8; margin-bottom:12px;">按照以下步骤获取您的 API Key：</p>'
            '<p style="color:#7dd3fc; font-weight:600; margin-bottom:4px;">第一步：注册账号</p>'
            '<p style="color:#a0b4c4; margin-bottom:12px;">'
            '访问 API 平台官网：<a href="https://www.hfsyapi.cn/" style="color:#7dd3fc;">https://www.hfsyapi.cn/</a><br>'
            '点击"注册"按钮创建账号，使用邮箱或手机号完成注册流程。</p>'
            '<p style="color:#7dd3fc; font-weight:600; margin-bottom:4px;">第二步：登录后台</p>'
            '<p style="color:#a0b4c4; margin-bottom:12px;">'
            '注册完成后登录 <a href="https://www.hfsyapi.cn/" style="color:#7dd3fc;">https://www.hfsyapi.cn/</a> 管理后台。<br>'
            '在左侧菜单中找到"API 管理"或"令牌管理"入口。</p>'
            '<p style="color:#7dd3fc; font-weight:600; margin-bottom:4px;">第三步：创建 API Key</p>'
            '<p style="color:#a0b4c4; margin-bottom:12px;">'
            '点击"创建新令牌"或"生成 API Key"按钮。<br>'
            '为令牌设置一个名称（如 "Glacier AI"）。<br>'
            '点击确认后，系统会生成一个以 <b style="color:#7dd3fc;">sk-</b> 开头的密钥。</p>'
            '<p style="color:#7dd3fc; font-weight:600; margin-bottom:4px;">第四步：复制并使用</p>'
            '<p style="color:#a0b4c4; margin-bottom:12px;">'
            '点击复制按钮，将 API Key 复制到剪贴板。<br>'
            '回到本软件，粘贴到输入框中，点击"开始使用"即可。</p>'
            '<p style="color:#ff6b6b; font-size:12px; margin-top:8px;">'
            '⚠ 请妥善保管您的 API Key，不要分享给他人。<br>'
            '如果密钥泄露，请立即到后台重新生成。</p>'
        )
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("我知道了")
        close_btn.setObjectName("closeBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)


class KeyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Glacier AI")
        self.setFixedSize(440, 420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(LOGIN_STYLE)

        logo_path = get_logo_path()
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 30, 30, 30)

        card = QFrame()
        card.setObjectName("loginCard")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(28, 32, 28, 28)

        title = QLabel("Glacier AI")
        title.setObjectName("loginTitle")
        card_layout.addWidget(title)

        subtitle = QLabel("New API - Image & Video Generator")
        subtitle.setObjectName("loginSubtitle")
        card_layout.addWidget(subtitle)

        version = QLabel("VERSION 2.7")
        version.setObjectName("loginVersion")
        card_layout.addWidget(version)

        card_layout.addSpacing(8)

        hint = QLabel("请输入您的 API Key")
        hint.setObjectName("loginHint")
        card_layout.addWidget(hint)

        self.key_input = QLineEdit()
        self.key_input.setObjectName("keyInput")
        self.key_input.setPlaceholderText("sk-xxxxxxxxxxxxxxxx")
        self.key_input.setMinimumHeight(42)
        self.key_input.setEchoMode(QLineEdit.Password)
        card_layout.addWidget(self.key_input)

        self.toggle_btn = QPushButton("显示")
        self.toggle_btn.setObjectName("toggleBtn")
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_visibility)
        card_layout.addWidget(self.toggle_btn, alignment=Qt.AlignRight)

        card_layout.addSpacing(4)

        self.login_btn = QPushButton("开始使用")
        self.login_btn.setObjectName("loginBtn")
        self.login_btn.setMinimumHeight(44)
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.clicked.connect(self.on_login)
        card_layout.addWidget(self.login_btn)

        self.tutorial_btn = QPushButton("如何获取 API Key？")
        self.tutorial_btn.setObjectName("tutorialBtn")
        self.tutorial_btn.setCursor(Qt.PointingHandCursor)
        self.tutorial_btn.clicked.connect(self.show_tutorial)
        card_layout.addWidget(self.tutorial_btn, alignment=Qt.AlignCenter)

        outer.addWidget(card)

    def toggle_visibility(self):
        if self.key_input.echoMode() == QLineEdit.Password:
            self.key_input.setEchoMode(QLineEdit.Normal)
            self.toggle_btn.setText("隐藏")
        else:
            self.key_input.setEchoMode(QLineEdit.Password)
            self.toggle_btn.setText("显示")

    def on_login(self):
        key = self.key_input.text().strip()
        if not key:
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Warning)
            mb.setWindowTitle("提示")
            mb.setText("请输入正确的 API Key")
            mb.exec_()
            return
        if not key.startswith("sk-"):
            mb = QMessageBox(self)
            mb.setIcon(QMessageBox.Warning)
            mb.setWindowTitle("提示")
            mb.setText("请输入正确的 API Key")
            mb.setInformativeText("API Key 格式不正确，应以 sk- 开头")
            mb.exec_()
            return
        self.accept()

    def get_key(self):
        return self.key_input.text().strip()

    def show_tutorial(self):
        dlg = TutorialDialog(self)
        dlg.exec_()


class UploadRefImageThread(QThread):
    finished_ok = pyqtSignal(str, str, bytes)
    failed = pyqtSignal(str, str)

    def __init__(self, api_key, file_path, tag=""):
        super().__init__()
        self.api_key = api_key
        self.file_path = file_path
        self.tag = tag

    def run(self):
        try:
            with open(self.file_path, "rb") as f:
                img_bytes = f.read()
        except Exception as e:
            self.failed.emit(self.tag, f"读取图片失败: {e}")
            return

        filename = os.path.basename(self.file_path)
        ext = os.path.splitext(filename)[1].lower().lstrip(".") or "png"
        if ext == "jpg":
            ext = "jpeg"
        mime = f"image/{ext}"
        try:
            resp = requests.post(
                FILE_UPLOAD_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (filename, img_bytes, mime)},
                timeout=120,
            )
        except Exception as e:
            self.failed.emit(self.tag, f"上传请求失败: {e}")
            return

        try:
            with open("debug_output.log", "a", encoding="utf-8") as _f:
                _f.write(f"[UPLOAD] status={resp.status_code}, body={resp.text[:400]}\n")
        except Exception:
            pass

        if resp.status_code != 200:
            self.failed.emit(self.tag, f"上传失败 ({resp.status_code}): {resp.text[:200]}")
            return
        try:
            data = resp.json()
        except Exception:
            self.failed.emit(self.tag, f"上传响应非 JSON: {resp.text[:200]}")
            return
        if not data.get("success"):
            self.failed.emit(self.tag, f"上传失败: {data.get('message') or '未知错误'}")
            return
        url = (data.get("data") or {}).get("url") or ""
        if not url:
            self.failed.emit(self.tag, "上传响应缺少 url")
            return
        self.finished_ok.emit(self.tag, url, img_bytes)


class GenerateThread(QThread):
    one_finished = pyqtSignal(int, bytes)
    progress = pyqtSignal(str)
    error = pyqtSignal(int, str)
    all_done = pyqtSignal()

    def __init__(self, api_key, model, prompt, size, quality, output_format, count=1, image_url=None):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.prompt = prompt
        self.size = size
        self.quality = quality
        self.output_format = output_format
        self.count = count
        self.image_url = image_url

    def _generate_one(self, index):
        print(f"[DEBUG] _generate_one({index}) started, image_url={'YES' if self.image_url else 'NO'}, model={self.model}", flush=True)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "prompt": self.prompt,
            "n": 1,
            "size": self.size,
            "quality": self.quality,
            "response_format": "b64_json",
            "output_format": self.output_format
        }
        if self.image_url:
            payload["reference_images"] = list(self.image_url)
            print(f"[DEBUG] POST {API_URL} (json, {len(self.image_url)} reference_images)", flush=True)
        else:
            print(f"[DEBUG] POST {API_URL} (json, no image)", flush=True)

        import time as _time
        max_retries = 2
        resp = None
        for attempt in range(max_retries + 1):
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=600)
            with open("debug_output.log", "a", encoding="utf-8") as _f:
                _f.write(f"[RESP] model={self.model}, status={resp.status_code}, body={resp.text[:500]}\n")
            print(f"[DEBUG] Response status={resp.status_code}, body={resp.text[:300]}", flush=True)
            if resp.status_code == 200:
                break
            if resp.status_code in (500, 502, 503) and attempt < max_retries:
                wait = (attempt + 1) * 3
                print(f"[DEBUG] Retry {attempt+1}/{max_retries} after {wait}s...", flush=True)
                self.progress.emit(f"第{index+1}张遇到服务器错误，{wait}秒后重试...")
                _time.sleep(wait)
            else:
                break

        if resp.status_code != 200:
            self.error.emit(index, f"第{index+1}张 API 错误 ({resp.status_code}): {resp.text[:200]}")
            return

        data = resp.json()
        if "data" not in data or len(data["data"]) == 0:
            self.error.emit(index, f"第{index+1}张 API 返回异常")
            return

        item = data["data"][0]
        if item.get("b64_json"):
            img_bytes = base64.b64decode(item["b64_json"])
            self.one_finished.emit(index, img_bytes)
        elif "url" in item or "file_id" in item:
            img_url = item.get("url", "")
            file_id = item.get("file_id", "")
            if img_url.startswith("http"):
                dl_url = img_url
            elif file_id:
                dl_url = f"https://www.hfsyapi.cn/v1/files/{file_id}/content"
            elif img_url.startswith("/"):
                dl_url = "https://www.hfsyapi.cn" + img_url
            else:
                dl_url = img_url
            print(f"[DEBUG] Downloading image from: {dl_url}", flush=True)
            dl_headers = {"Authorization": f"Bearer {self.api_key}"}
            img_resp = requests.get(dl_url, headers=dl_headers, timeout=120)
            print(f"[DEBUG] Download status={img_resp.status_code}, content_length={len(img_resp.content)}, content_type={img_resp.headers.get('content-type','?')}", flush=True)
            if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                content_type = img_resp.headers.get("content-type", "")
                if "image" in content_type or "octet-stream" in content_type or dl_url.endswith(".png") or dl_url.split("?")[0].endswith(".png") or dl_url.split("?")[0].endswith(".jpg"):
                    self.one_finished.emit(index, img_resp.content)
                else:
                    header = img_resp.content[:8]
                    is_png = header[:4] == b'\x89PNG'
                    is_jpg = header[:2] == b'\xff\xd8'
                    is_webp = header[8:12] == b'WEBP' if len(header) >= 12 else False
                    if is_png or is_jpg or is_webp:
                        self.one_finished.emit(index, img_resp.content)
                    elif file_id:
                        print(f"[DEBUG] Not an image, trying file_id fallback...", flush=True)
                        fb_url = f"https://www.hfsyapi.cn/v1/files/{file_id}/content"
                        fb_resp = requests.get(fb_url, headers=dl_headers, timeout=120)
                        if fb_resp.status_code == 200 and len(fb_resp.content) > 2000:
                            self.one_finished.emit(index, fb_resp.content)
                        else:
                            self.error.emit(index, f"第{index+1}张下载失败")
                    else:
                        self.error.emit(index, f"第{index+1}张下载失败(非图片)")
            elif img_resp.status_code == 200:
                self.error.emit(index, f"第{index+1}张下载内容为空")
            else:
                print(f"[DEBUG] Download failed body={img_resp.text[:200]}", flush=True)
                self.error.emit(index, f"第{index+1}张下载失败 ({img_resp.status_code})")
        else:
            self.error.emit(index, f"第{index+1}张未知格式")

    def run(self):
        import threading, time
        threads = []
        for i in range(self.count):
            if i > 0:
                time.sleep(0.05)
            self.progress.emit(f"正在启动第 {i+1}/{self.count} 张生成...")
            t = threading.Thread(target=self._safe_generate, args=(i,))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        self.all_done.emit()

    def _safe_generate(self, index):
        try:
            self._generate_one(index)
        except requests.exceptions.Timeout:
            print(f"[DEBUG] _safe_generate({index}) Timeout", flush=True)
            self.error.emit(index, f"第{index+1}张请求超时")
        except requests.exceptions.ConnectionError:
            print(f"[DEBUG] _safe_generate({index}) ConnectionError", flush=True)
            self.error.emit(index, f"第{index+1}张网络连接失败")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[DEBUG] _safe_generate({index}) Exception: {e}\n{tb}", flush=True)
            with open("debug_output.log", "a", encoding="utf-8") as _f:
                _f.write(f"[EXCEPTION] index={index}: {e}\n{tb}\n")
            self.error.emit(index, f"第{index+1}张错误: {str(e)}")


class VideoGenerateThread(QThread):
    one_finished = pyqtSignal(int, bytes)
    progress = pyqtSignal(str)
    error = pyqtSignal(int, str)
    all_done = pyqtSignal()

    def __init__(self, api_key, prompt, size, duration, count=1, image_url=None):
        super().__init__()
        self.api_key = api_key
        self.prompt = prompt
        self.size = size
        self.duration = duration
        self.count = count
        self.image_url = image_url

    def _generate_one(self, index):
        import time
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "sora-2",
            "prompt": self.prompt,
            "orientation": self.size,
            "size": "1080p",
            "duration": int(self.duration),
            "watermark": False,
        }
        if self.image_url:
            payload["images"] = [self.image_url] if isinstance(self.image_url, str) else list(self.image_url)

        def _log(tag, content):
            try:
                with open("debug_output.log", "a", encoding="utf-8") as _f:
                    _f.write(f"[VIDEO {tag}] index={index}: {content}\n")
            except Exception:
                pass

        self.progress.emit(f"第{index+1}个视频: 正在提交请求...")
        resp = requests.post(VIDEO_API_URL, headers=headers, json=payload, timeout=600)
        _log("POST", f"status={resp.status_code}, body={resp.text[:800]}")
        if resp.status_code != 200:
            self.error.emit(index, f"第{index+1}个 API 错误 ({resp.status_code}): {resp.text[:300]}")
            return

        data = resp.json()
        task_id = data.get("id") or data.get("task_id")
        if isinstance(data.get("data"), dict):
            task_id = task_id or data["data"].get("id")
        if not task_id:
            _log("NO_TASK_ID", f"data={json.dumps(data, ensure_ascii=False)[:600]}")
            self.error.emit(index, f"第{index+1}个 API 返回异常: 无法识别 task_id")
            return

        self.progress.emit(f"第{index+1}个视频: 任务已提交，等待生成...")
        query_url = f"https://www.hfsyapi.cn/v1/video/query?id={task_id}"

        for i in range(120):
            time.sleep(5)
            try:
                poll_resp = requests.get(query_url, headers=headers, timeout=30)
            except Exception as e:
                _log("POLL_ERR", f"i={i}, err={e}")
                continue
            if poll_resp.status_code != 200:
                _log("POLL_HTTP", f"i={i}, status={poll_resp.status_code}, body={poll_resp.text[:300]}")
                continue
            try:
                poll_data = poll_resp.json()
            except Exception as e:
                _log("POLL_JSON_ERR", f"i={i}, err={e}, body={poll_resp.text[:300]}")
                continue

            inner = poll_data.get("data") if isinstance(poll_data.get("data"), dict) else {}
            status = str(inner.get("status") or poll_data.get("status") or "").lower()
            video_url = inner.get("video_url") or poll_data.get("video_url") or ""
            if not video_url:
                detail = inner.get("detail") if isinstance(inner.get("detail"), dict) else {}
                video_url = detail.get("url") or ""
            progress_pct = inner.get("progress", 0)

            if status == "completed":
                if not video_url:
                    _log("NO_URL", f"poll_data={json.dumps(poll_data, ensure_ascii=False)[:600]}")
                    self.error.emit(index, f"第{index+1}个任务完成但未返回视频地址")
                    return
                self.progress.emit(f"第{index+1}个视频: 正在下载...")
                vid_resp = requests.get(video_url, timeout=300)
                if vid_resp.status_code == 200:
                    self.one_finished.emit(index, vid_resp.content)
                else:
                    self.error.emit(index, f"第{index+1}个视频下载失败 ({vid_resp.status_code})")
                return
            if status == "failed":
                err_msg = inner.get("error") or inner.get("message") or poll_data.get("message") or "未知错误"
                self.error.emit(index, f"第{index+1}个视频生成失败: {err_msg}")
                return
            self.progress.emit(f"第{index+1}个视频: 生成中... ({(i+1) * 5}s, {progress_pct}%, {status or 'pending'})")

        self.error.emit(index, f"第{index+1}个视频生成超时")

    def _safe_generate(self, index):
        try:
            self._generate_one(index)
        except requests.exceptions.Timeout:
            self.error.emit(index, f"第{index+1}个视频请求超时")
        except requests.exceptions.ConnectionError:
            self.error.emit(index, f"第{index+1}个视频网络连接失败")
        except Exception as e:
            self.error.emit(index, f"第{index+1}个视频错误: {str(e)}")

    def run(self):
        import threading, time
        threads = []
        for i in range(self.count):
            if i > 0:
                time.sleep(0.05)
            self.progress.emit(f"正在启动第 {i+1}/{self.count} 个视频生成...")
            t = threading.Thread(target=self._safe_generate, args=(i,))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        self.all_done.emit()


class ClickableLabel(QLabel):
    def __init__(self, raw_bytes, file_ext="png", is_video=False, parent=None):
        super().__init__(parent)
        self.raw_bytes = raw_bytes
        self.file_ext = file_ext
        self.is_video = is_video
        self.checked = False
        self.setObjectName("thumbLabel")
        self.setCursor(Qt.PointingHandCursor)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(150, 150)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.checked = not self.checked
            self._update_border()
        super().mousePressEvent(event)

    def _update_border(self):
        if hasattr(self, '_vid_style_base'):
            if self.checked:
                self.setStyleSheet(self._vid_style_checked)
            else:
                self.setStyleSheet(self._vid_style_base)
        else:
            if self.checked:
                self.setStyleSheet("border: 3px solid #7dd3fc; border-radius: 8px;")
            else:
                self.setStyleSheet("border: none;")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            dlg = PreviewDialog(self.raw_bytes, self.file_ext, self.is_video, self.window())
            dlg.exec_()

    def _show_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #141c2e; border: 1px solid rgba(125,211,252,0.15); color: #e0e8f0; padding: 4px; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #2d3748; }
        """)
        save_action = menu.addAction("保存")
        action = menu.exec_(self.mapToGlobal(pos))
        if action == save_action:
            self._save_file()

    def _save_file(self):
        if self.is_video:
            name = f"sora_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            filters = "MP4 视频 (*.mp4);;所有文件 (*)"
        else:
            name = f"gpt_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{self.file_ext}"
            if self.file_ext == "png":
                filters = "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;所有文件 (*)"
            else:
                filters = "JPEG 图片 (*.jpg);;PNG 图片 (*.png);;所有文件 (*)"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存文件",
            os.path.join(os.path.expanduser("~"), "Desktop", name),
            filters
        )
        if path:
            with open(path, "wb") as f:
                f.write(self.raw_bytes)


class PreviewDialog(QDialog):
    def __init__(self, raw_bytes, file_ext="png", is_video=False, parent=None):
        super().__init__(parent)
        self.raw_bytes = raw_bytes
        self.file_ext = file_ext
        self.is_video = is_video
        self.setWindowTitle("预览")
        self.setMinimumSize(600, 500)
        self.resize(900, 700)
        self.setStyleSheet("QDialog { background-color: #0a0e1a; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if is_video:
            info = QLabel()
            info.setAlignment(Qt.AlignCenter)
            size_kb = len(raw_bytes) / 1024
            size_str = f"{size_kb / 1024:.1f} MB" if size_kb > 1024 else f"{size_kb:.0f} KB"
            info.setText(f"🎬 视频文件\n\n大小: {size_str}\n\n保存到本地后可播放")
            info.setStyleSheet("color: #e0e8f0; font-size: 16px; background: transparent;")
            layout.addWidget(info, 1)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; background: #0a0e1a; }")
            img_label = QLabel()
            img_label.setAlignment(Qt.AlignCenter)
            img_label.setStyleSheet("background: transparent;")
            qimg = QImage.fromData(raw_bytes)
            if not qimg.isNull():
                pixmap = QPixmap.fromImage(qimg)
                screen_w = self.width() - 40
                if pixmap.width() > screen_w:
                    pixmap = pixmap.scaledToWidth(screen_w, Qt.SmoothTransformation)
                img_label.setPixmap(pixmap)
            scroll.setWidget(img_label)
            layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 12, 16, 12)
        btn_row.addStretch()
        save_btn = QPushButton("保存")
        save_btn.setObjectName("refBtn")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("refBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _save(self):
        if self.is_video:
            name = f"sora_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            filters = "MP4 视频 (*.mp4);;所有文件 (*)"
        else:
            name = f"gpt_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{self.file_ext}"
            if self.file_ext == "png":
                filters = "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;所有文件 (*)"
            else:
                filters = "JPEG 图片 (*.jpg);;PNG 图片 (*.png);;所有文件 (*)"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存文件",
            os.path.join(os.path.expanduser("~"), "Desktop", name),
            filters
        )
        if path:
            with open(path, "wb") as f:
                f.write(self.raw_bytes)


if getattr(sys, 'frozen', False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))

HISTORY_DIR = os.path.join(_APP_DIR, "history")
HISTORY_JSON = os.path.join(HISTORY_DIR, "history.json")


def ensure_history_dir():
    os.makedirs(HISTORY_DIR, exist_ok=True)


def load_history():
    ensure_history_dir()
    if os.path.exists(HISTORY_JSON):
        try:
            with open(HISTORY_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(records):
    ensure_history_dir()
    with open(HISTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def add_history_record(prompt, model, quality, ratio, img_paths, kind="image"):
    records = load_history()
    records.insert(0, {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "prompt": prompt,
        "model": model,
        "quality": quality,
        "ratio": ratio,
        "kind": kind,
        "images": img_paths,
    })
    if len(records) > 200:
        records = records[:200]
    save_history(records)


def add_video_history_record(prompt, model, orientation, duration, video_paths):
    add_history_record(
        prompt=prompt,
        model=model,
        quality=f"{duration}s",
        ratio=orientation,
        img_paths=video_paths,
        kind="video",
    )


class MainWindow(QMainWindow):
    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key
        self.image_data_list = []
        self.video_data_list = []
        self.thread = None
        self.video_thread = None
        self._drag_pos = None
        self._img_ref_data_list = []
        self._vid_ref_data = None
        self._current_prompt = ""
        self._current_model = ""
        self._current_quality = ""
        self._current_ratio = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Glacier AI")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 800)
        self.setStyleSheet(DARK_STYLE)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        logo_path = get_logo_path()
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        central = QWidget()
        central.setStyleSheet("background-color: #0a0e1a;")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        self._build_title_bar(root)

        body = QHBoxLayout()
        body.setSpacing(0)
        body.setContentsMargins(0, 0, 0, 0)

        self._build_side_nav(body)

        right_area = QVBoxLayout()
        right_area.setSpacing(0)
        right_area.setContentsMargins(0, 0, 0, 0)

        self.content_stack = QStackedWidget()
        self._build_image_page()
        self._build_video_page()
        self._build_history_page()
        right_area.addWidget(self.content_stack)

        self._build_footer(right_area)

        body.addLayout(right_area)
        root.addLayout(body)

    def _build_title_bar(self, parent_layout):
        bar = QFrame()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(40)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(0)

        brand = QLabel("Glacier AI")
        brand.setObjectName("titleBrand")
        layout.addWidget(brand)

        sep = QFrame()
        sep.setFixedSize(1, 16)
        sep.setStyleSheet("background-color: rgba(125, 211, 252, 0.2);")
        layout.addSpacing(12)
        layout.addWidget(sep)
        layout.addSpacing(12)

        sub = QLabel("New API - 图片视频生成器")
        sub.setObjectName("titleSub")
        layout.addWidget(sub)

        layout.addStretch()

        btn_min = QPushButton("—")
        btn_min.setObjectName("winBtn")
        btn_min.setFixedSize(46, 40)
        btn_min.setCursor(Qt.PointingHandCursor)
        btn_min.clicked.connect(self.showMinimized)
        layout.addWidget(btn_min)

        self._btn_max = QPushButton("☐")
        self._btn_max.setObjectName("winBtn")
        self._btn_max.setFixedSize(46, 40)
        self._btn_max.setCursor(Qt.PointingHandCursor)
        self._btn_max.clicked.connect(self._toggle_maximize)
        layout.addWidget(self._btn_max)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("winBtnClose")
        btn_close.setFixedSize(46, 40)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

        bar.mousePressEvent = self._title_mouse_press
        bar.mouseMoveEvent = self._title_mouse_move
        bar.mouseDoubleClickEvent = lambda e: self._toggle_maximize()

        parent_layout.addWidget(bar)

    def _title_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def _title_mouse_move(self, event):
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            if self.isMaximized():
                self.showNormal()
            self.move(event.globalPos() - self._drag_pos)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _build_side_nav(self, parent_layout):
        nav = QFrame()
        nav.setObjectName("sideNav")
        nav.setFixedWidth(200)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 20, 20, 12)
        header_layout.setSpacing(2)
        title = QLabel("GLACIER ENGINE")
        title.setObjectName("navTitle")
        header_layout.addWidget(title)
        ver = QLabel("V2.7 Stable")
        ver.setObjectName("navVersion")
        ver.setStyleSheet("font-size: 16px; font-weight: bold; color: #ff9f1c;")
        header_layout.addWidget(ver)
        nav_layout.addWidget(header)

        nav_layout.addSpacing(4)

        self.nav_img_btn = QPushButton("  ⚡  图片生成")
        self.nav_img_btn.setObjectName("navBtnActive")
        self.nav_img_btn.setCursor(Qt.PointingHandCursor)
        self.nav_img_btn.clicked.connect(lambda: self._switch_nav(0))
        nav_layout.addWidget(self.nav_img_btn)

        self.nav_vid_btn = QPushButton("  🎬  视频生成")
        self.nav_vid_btn.setObjectName("navBtn")
        self.nav_vid_btn.setCursor(Qt.PointingHandCursor)
        self.nav_vid_btn.clicked.connect(lambda: self._switch_nav(1))
        nav_layout.addWidget(self.nav_vid_btn)

        self.nav_hist_btn = QPushButton("  📋  历史记录")
        self.nav_hist_btn.setObjectName("navBtn")
        self.nav_hist_btn.setCursor(Qt.PointingHandCursor)
        self.nav_hist_btn.clicked.connect(lambda: self._switch_nav(2))
        nav_layout.addWidget(self.nav_hist_btn)

        nav_layout.addStretch()

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 12, 16, 16)
        bottom_layout.setSpacing(6)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,0.05);")
        bottom_layout.addWidget(sep)
        bottom_layout.addSpacing(4)

        key_display = self.api_key[:8] + "..." + self.api_key[-4:]
        key_label = QLabel(f"Key: {key_display}")
        key_label.setObjectName("navKeyLabel")
        bottom_layout.addWidget(key_label)

        nav_layout.addWidget(bottom)
        parent_layout.addWidget(nav)

    def _switch_nav(self, index):
        self.content_stack.setCurrentIndex(index)
        btns = [self.nav_img_btn, self.nav_vid_btn, self.nav_hist_btn]
        for i, btn in enumerate(btns):
            btn.setObjectName("navBtnActive" if i == index else "navBtn")
            btn.setStyle(btn.style())
        if index == 2:
            self._refresh_history_page()

    def _build_image_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: #0a0e1a;")
        layout = QHBoxLayout(page)
        layout.setSpacing(24)
        layout.setContentsMargins(24, 24, 24, 0)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_inner = QWidget()
        left_inner.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_inner)
        left_layout.setSpacing(16)
        left_layout.setContentsMargins(0, 0, 0, 0)

        prompt_card = QFrame()
        prompt_card.setObjectName("glassPanel")
        pc_layout = QVBoxLayout(prompt_card)
        pc_layout.setSpacing(10)
        pc_layout.setContentsMargins(20, 20, 20, 20)

        ph = QHBoxLayout()
        pl = QLabel("提示词 Prompt")
        pl.setObjectName("sectionLabel")
        ph.addWidget(pl)
        ph.addStretch()
        badge = QLabel("ENHANCED")
        badge.setObjectName("sectionBadge")
        ph.addWidget(badge)
        pc_layout.addLayout(ph)

        self.prompt_input = PlainPasteTextEdit()
        self.prompt_input.setObjectName("promptInput")
        self.prompt_input.setPlaceholderText("描述你想要生成的图片，例如：一只在月球上弹吉他的猫，赛博朋克风格...")
        self.prompt_input.setMinimumHeight(120)
        self.prompt_input.setMaximumHeight(160)
        self.prompt_input.setAcceptRichText(False)
        pc_layout.addWidget(self.prompt_input)
        left_layout.addWidget(prompt_card)

        ref_card = QFrame()
        ref_card.setObjectName("glassPanel")
        ref_layout = QVBoxLayout(ref_card)
        ref_layout.setSpacing(10)
        ref_layout.setContentsMargins(20, 20, 20, 20)

        ref_title = QLabel("参考图片（可选）")
        ref_title.setObjectName("sectionLabel")
        ref_layout.addWidget(ref_title)

        self.img_ref_hint = QLabel("提示：参考图最多 4 张")
        self.img_ref_hint.setStyleSheet("color: #f59e0b; font-size: 11px;")
        ref_layout.addWidget(self.img_ref_hint)

        self.img_ref_url = QLineEdit()
        self.img_ref_url.setObjectName("refUrlInput")
        self.img_ref_url.setPlaceholderText("粘贴图片 URL 或选择本地图片...")
        ref_layout.addWidget(self.img_ref_url)

        btn_row = QHBoxLayout()
        self.img_ref_pick_btn = QPushButton("选择本地图片")
        self.img_ref_pick_btn.setObjectName("refBtn")
        self.img_ref_pick_btn.setCursor(Qt.PointingHandCursor)
        self.img_ref_pick_btn.clicked.connect(self.on_pick_img_ref)
        btn_row.addWidget(self.img_ref_pick_btn)
        btn_row.addStretch()
        self.img_ref_clear_btn = QPushButton("清除")
        self.img_ref_clear_btn.setObjectName("refBtn")
        self.img_ref_clear_btn.setCursor(Qt.PointingHandCursor)
        self.img_ref_clear_btn.clicked.connect(self.on_clear_img_ref)
        btn_row.addWidget(self.img_ref_clear_btn)
        ref_layout.addLayout(btn_row)

        self.img_ref_preview_layout = QGridLayout()
        self.img_ref_preview_layout.setSpacing(6)
        self.img_ref_preview_layout.setAlignment(Qt.AlignLeft)
        ref_layout.addLayout(self.img_ref_preview_layout)

        self.img_ref_count_label = QLabel("")
        self.img_ref_count_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        ref_layout.addWidget(self.img_ref_count_label)

        left_layout.addWidget(ref_card)

        param_card = QFrame()
        param_card.setObjectName("glassPanel")
        pm_layout = QVBoxLayout(param_card)
        pm_layout.setSpacing(14)
        pm_layout.setContentsMargins(20, 20, 20, 20)

        pm_title = QLabel("参数设置")
        pm_title.setObjectName("sectionLabel")
        pm_layout.addWidget(pm_title)

        grid = QGridLayout()
        grid.setSpacing(12)

        l1 = QLabel("模型")
        l1.setObjectName("paramLabel")
        grid.addWidget(l1, 0, 0)
        self.model_combo = QComboBox()
        setup_combo(self.model_combo)
        self.model_combo.addItems(["gpt-image-2", "gpt-image-2pro"])
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        grid.addWidget(self.model_combo, 1, 0)

        l2 = QLabel("比例")
        l2.setObjectName("paramLabel")
        grid.addWidget(l2, 0, 1)
        self.size_combo = QComboBox()
        setup_combo(self.size_combo)
        self.size_combo.addItems(RATIO_LIST)
        grid.addWidget(self.size_combo, 1, 1)

        l3 = QLabel("质量")
        l3.setObjectName("paramLabel")
        grid.addWidget(l3, 2, 0)
        self.quality_combo = QComboBox()
        setup_combo(self.quality_combo)
        self.quality_combo.addItems(MODEL_QUALITY["gpt-image-2"])
        grid.addWidget(self.quality_combo, 3, 0)

        l4 = QLabel("生成格式")
        l4.setObjectName("paramLabel")
        grid.addWidget(l4, 2, 1)
        self.format_combo = QComboBox()
        setup_combo(self.format_combo)
        self.format_combo.addItems(["png", "jpeg"])
        grid.addWidget(self.format_combo, 3, 1)

        l5 = QLabel("生成数量")
        l5.setObjectName("paramLabel")
        grid.addWidget(l5, 4, 0)
        self.img_count_combo = QComboBox()
        setup_combo(self.img_count_combo)
        self.img_count_combo.addItems([str(i) for i in range(1, 11)])
        grid.addWidget(self.img_count_combo, 5, 0)

        pm_layout.addLayout(grid)
        pm_layout.addSpacing(8)

        self.gen_btn = QPushButton("⚡  生成图片")
        self.gen_btn.setObjectName("generateBtn")
        self.gen_btn.setMinimumHeight(56)
        self.gen_btn.setCursor(Qt.PointingHandCursor)
        self.gen_btn.clicked.connect(self.on_generate)
        pm_layout.addWidget(self.gen_btn)

        left_layout.addWidget(param_card)
        left_layout.addStretch()
        left_scroll.setWidget(left_inner)

        right = QVBoxLayout()
        right.setSpacing(0)
        right.setContentsMargins(0, 0, 0, 0)

        save_row = QHBoxLayout()
        save_row.addStretch()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setObjectName("saveBtn")
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_btn.clicked.connect(self.on_select_all_images)
        save_row.addWidget(self.select_all_btn)
        self.save_btn = QPushButton("保存选中")
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.setEnabled(False)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.on_save)
        save_row.addWidget(self.save_btn)
        right.addLayout(save_row)
        right.addSpacing(8)

        preview = QFrame()
        preview.setObjectName("previewArea")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(24, 24, 24, 24)

        self.img_placeholder = QWidget()
        ph_layout = QVBoxLayout(self.img_placeholder)
        ph_layout.setAlignment(Qt.AlignCenter)
        ph_layout.setSpacing(12)
        img_icon_holder = QWidget()
        img_icon_holder.setFixedSize(200, 110)
        img_icon_holder.setStyleSheet("background: transparent;")
        self.img_search_icon = QLabel("🔍", img_icon_holder)
        self.img_search_icon.setAlignment(Qt.AlignCenter)
        self.img_search_icon.setStyleSheet("font-size: 48px; border: none; background: transparent;")
        self.img_search_icon.setFixedSize(70, 70)
        self.img_search_icon.move(65, 35)
        self._img_icon_home = (65, 35)
        self._img_icon_opacity = QGraphicsOpacityEffect(self.img_search_icon)
        self._img_icon_opacity.setOpacity(1.0)
        self.img_search_icon.setGraphicsEffect(self._img_icon_opacity)
        ph_layout.addWidget(img_icon_holder, alignment=Qt.AlignCenter)
        t1 = QLabel("等待生成")
        t1.setObjectName("previewTitle")
        t1.setAlignment(Qt.AlignCenter)
        ph_layout.addWidget(t1)
        t2 = QLabel("输入提示词并调整参数，生成高质量 AI 图片")
        t2.setObjectName("previewDesc")
        t2.setAlignment(Qt.AlignCenter)
        t2.setWordWrap(True)
        ph_layout.addWidget(t2)

        self.img_results_container = QWidget()
        self.img_results_container.setStyleSheet("background: transparent;")
        self.img_results_layout = QGridLayout(self.img_results_container)
        self.img_results_layout.setSpacing(8)
        self.img_results_layout.setContentsMargins(8, 8, 8, 8)
        self.img_results_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        img_scroll = QScrollArea()
        img_scroll.setWidgetResizable(True)
        img_scroll.setWidget(self.img_results_container)

        self.img_stack = QStackedWidget()
        self.img_stack.addWidget(self.img_placeholder)
        self.img_stack.addWidget(img_scroll)

        preview_layout.addWidget(self.img_stack)

        self.img_status_bar = QLabel("● GPU Cluster: Online          Session: Frost-772")
        self.img_status_bar.setObjectName("footerText")
        self.img_status_bar.setStyleSheet("border-top: 1px solid rgba(255,255,255,0.05); padding-top: 8px; color: #64748b; font-size: 9px; font-family: Consolas;")
        preview_layout.addWidget(self.img_status_bar)

        right.addWidget(preview, 1)

        layout.addWidget(left_scroll, 4)
        layout.addLayout(right, 6)
        self.content_stack.addWidget(page)

    def _build_video_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: #0a0e1a;")
        layout = QHBoxLayout(page)
        layout.setSpacing(24)
        layout.setContentsMargins(24, 24, 24, 0)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_inner = QWidget()
        left_inner.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_inner)
        left_layout.setSpacing(16)
        left_layout.setContentsMargins(0, 0, 0, 0)

        prompt_card = QFrame()
        prompt_card.setObjectName("glassPanel")
        pc_layout = QVBoxLayout(prompt_card)
        pc_layout.setSpacing(10)
        pc_layout.setContentsMargins(20, 20, 20, 20)

        ph = QHBoxLayout()
        pl = QLabel("提示词 Prompt")
        pl.setObjectName("sectionLabel")
        ph.addWidget(pl)
        ph.addStretch()
        badge = QLabel("VIDEO")
        badge.setObjectName("sectionBadge")
        ph.addWidget(badge)
        pc_layout.addLayout(ph)

        self.video_prompt_input = PlainPasteTextEdit()
        self.video_prompt_input.setObjectName("promptInput")
        self.video_prompt_input.setPlaceholderText("描述你想要生成的视频，例如：一只猫在海边奔跑，慢动作，电影质感...")
        self.video_prompt_input.setMinimumHeight(120)
        self.video_prompt_input.setMaximumHeight(160)
        self.video_prompt_input.setAcceptRichText(False)
        pc_layout.addWidget(self.video_prompt_input)
        left_layout.addWidget(prompt_card)

        vid_ref_card = QFrame()
        vid_ref_card.setObjectName("glassPanel")
        vid_ref_layout = QVBoxLayout(vid_ref_card)
        vid_ref_layout.setSpacing(10)
        vid_ref_layout.setContentsMargins(20, 20, 20, 20)

        vid_ref_title = QLabel("参考图片（可选）")
        vid_ref_title.setObjectName("sectionLabel")
        vid_ref_layout.addWidget(vid_ref_title)

        self.vid_ref_url = QLineEdit()
        self.vid_ref_url.setObjectName("refUrlInput")
        self.vid_ref_url.setPlaceholderText("粘贴图片 URL 或选择本地图片...")
        vid_ref_layout.addWidget(self.vid_ref_url)

        vid_btn_row = QHBoxLayout()
        self.vid_ref_pick_btn = QPushButton("选择本地图片")
        self.vid_ref_pick_btn.setObjectName("refBtn")
        self.vid_ref_pick_btn.setCursor(Qt.PointingHandCursor)
        self.vid_ref_pick_btn.clicked.connect(self.on_pick_vid_ref)
        vid_btn_row.addWidget(self.vid_ref_pick_btn)
        vid_btn_row.addStretch()
        self.vid_ref_clear_btn = QPushButton("清除")
        self.vid_ref_clear_btn.setObjectName("refBtn")
        self.vid_ref_clear_btn.setCursor(Qt.PointingHandCursor)
        self.vid_ref_clear_btn.clicked.connect(self.on_clear_vid_ref)
        vid_btn_row.addWidget(self.vid_ref_clear_btn)
        vid_ref_layout.addLayout(vid_btn_row)

        self.vid_ref_preview = QLabel()
        self.vid_ref_preview.setAlignment(Qt.AlignCenter)
        self.vid_ref_preview.setMaximumHeight(160)
        self.vid_ref_preview.setStyleSheet("border: none; background: transparent;")
        vid_ref_layout.addWidget(self.vid_ref_preview)

        left_layout.addWidget(vid_ref_card)

        param_card = QFrame()
        param_card.setObjectName("glassPanel")
        pm_layout = QVBoxLayout(param_card)
        pm_layout.setSpacing(14)
        pm_layout.setContentsMargins(20, 20, 20, 20)

        pm_title = QLabel("参数设置")
        pm_title.setObjectName("sectionLabel")
        pm_layout.addWidget(pm_title)

        grid = QGridLayout()
        grid.setSpacing(12)

        l1 = QLabel("模型")
        l1.setObjectName("paramLabel")
        grid.addWidget(l1, 0, 0)
        self.video_model_combo = QComboBox()
        setup_combo(self.video_model_combo)
        self.video_model_combo.addItems(["sora-2"])
        grid.addWidget(self.video_model_combo, 1, 0)

        l2 = QLabel("画面方向")
        l2.setObjectName("paramLabel")
        grid.addWidget(l2, 0, 1)
        self.video_size_combo = QComboBox()
        setup_combo(self.video_size_combo)
        self.video_size_combo.addItems(list(VIDEO_SIZES.keys()))
        grid.addWidget(self.video_size_combo, 1, 1)

        l3 = QLabel("时长（秒）")
        l3.setObjectName("paramLabel")
        grid.addWidget(l3, 2, 0)
        self.video_duration_combo = QComboBox()
        setup_combo(self.video_duration_combo)
        self.video_duration_combo.addItems(VIDEO_DURATIONS)
        grid.addWidget(self.video_duration_combo, 3, 0)

        l4 = QLabel("生成数量")
        l4.setObjectName("paramLabel")
        grid.addWidget(l4, 2, 1)
        self.vid_count_combo = QComboBox()
        setup_combo(self.vid_count_combo)
        self.vid_count_combo.addItems([str(i) for i in range(1, 6)])
        grid.addWidget(self.vid_count_combo, 3, 1)

        pm_layout.addLayout(grid)
        pm_layout.addSpacing(8)

        self.video_gen_btn = QPushButton("⚡  生成视频")
        self.video_gen_btn.setObjectName("generateBtn")
        self.video_gen_btn.setMinimumHeight(56)
        self.video_gen_btn.setCursor(Qt.PointingHandCursor)
        self.video_gen_btn.clicked.connect(self.on_generate_video)
        pm_layout.addWidget(self.video_gen_btn)

        left_layout.addWidget(param_card)
        left_layout.addStretch()
        left_scroll.setWidget(left_inner)

        right = QVBoxLayout()
        right.setSpacing(0)
        right.setContentsMargins(0, 0, 0, 0)

        save_row = QHBoxLayout()
        save_row.addStretch()
        self.vid_select_all_btn = QPushButton("全选")
        self.vid_select_all_btn.setObjectName("saveBtn")
        self.vid_select_all_btn.setCursor(Qt.PointingHandCursor)
        self.vid_select_all_btn.clicked.connect(self.on_select_all_videos)
        save_row.addWidget(self.vid_select_all_btn)
        self.video_save_btn = QPushButton("保存选中")
        self.video_save_btn.setObjectName("saveBtn")
        self.video_save_btn.setEnabled(False)
        self.video_save_btn.setCursor(Qt.PointingHandCursor)
        self.video_save_btn.clicked.connect(self.on_save_video)
        save_row.addWidget(self.video_save_btn)
        right.addLayout(save_row)
        right.addSpacing(8)

        preview = QFrame()
        preview.setObjectName("previewArea")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(24, 24, 24, 24)

        self.video_status_label = QLabel()
        self.video_status_label.setAlignment(Qt.AlignCenter)
        self.video_status_label.setStyleSheet("border: none; background: transparent;")

        self.vid_placeholder = QWidget()
        vph_layout = QVBoxLayout(self.vid_placeholder)
        vph_layout.setAlignment(Qt.AlignCenter)
        vph_layout.setSpacing(12)
        vid_icon_holder = QWidget()
        vid_icon_holder.setFixedSize(200, 110)
        vid_icon_holder.setStyleSheet("background: transparent;")
        self.vid_search_icon = QLabel("🎬", vid_icon_holder)
        self.vid_search_icon.setAlignment(Qt.AlignCenter)
        self.vid_search_icon.setStyleSheet("font-size: 48px; border: none; background: transparent;")
        self.vid_search_icon.setFixedSize(70, 70)
        self.vid_search_icon.move(65, 35)
        self._vid_icon_home = (65, 35)
        self._vid_icon_opacity = QGraphicsOpacityEffect(self.vid_search_icon)
        self._vid_icon_opacity.setOpacity(1.0)
        self.vid_search_icon.setGraphicsEffect(self._vid_icon_opacity)
        vph_layout.addWidget(vid_icon_holder, alignment=Qt.AlignCenter)
        self.vid_placeholder_title = QLabel("等待生成")
        self.vid_placeholder_title.setObjectName("previewTitle")
        self.vid_placeholder_title.setAlignment(Qt.AlignCenter)
        vph_layout.addWidget(self.vid_placeholder_title)
        self.vid_placeholder_desc = QLabel("输入提示词并调整参数，生成高质量 AI 视频")
        self.vid_placeholder_desc.setObjectName("previewDesc")
        self.vid_placeholder_desc.setAlignment(Qt.AlignCenter)
        self.vid_placeholder_desc.setWordWrap(True)
        vph_layout.addWidget(self.vid_placeholder_desc)

        self.vid_results_container = QWidget()
        self.vid_results_container.setStyleSheet("background: transparent;")
        self.vid_results_layout = QGridLayout(self.vid_results_container)
        self.vid_results_layout.setSpacing(8)
        self.vid_results_layout.setContentsMargins(8, 8, 8, 8)
        self.vid_results_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        vid_scroll = QScrollArea()
        vid_scroll.setWidgetResizable(True)
        vid_scroll.setWidget(self.vid_results_container)

        self.vid_stack = QStackedWidget()
        self.vid_stack.addWidget(self.vid_placeholder)
        self.vid_stack.addWidget(vid_scroll)
        self.vid_stack.addWidget(self.video_status_label)

        preview_layout.addWidget(self.vid_stack)

        self.vid_status_bar = QLabel("● GPU Cluster: Online          Session: Frost-772")
        self.vid_status_bar.setObjectName("footerText")
        self.vid_status_bar.setStyleSheet("border-top: 1px solid rgba(255,255,255,0.05); padding-top: 8px; color: #64748b; font-size: 9px; font-family: Consolas;")
        preview_layout.addWidget(self.vid_status_bar)

        right.addWidget(preview, 1)

        layout.addWidget(left_scroll, 4)
        layout.addLayout(right, 6)
        self.content_stack.addWidget(page)

    def _build_footer(self, parent_layout):
        footer = QFrame()
        footer.setObjectName("footerBar")
        footer.setFixedHeight(36)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 0, 20, 0)

        self.footer_status = QLabel("就绪")
        self.footer_status.setObjectName("footerText")
        fl.addWidget(self.footer_status)

        fl.addStretch()

        brand = QLabel("GLACIER-OS CORE V2.7.0")
        brand.setObjectName("footerBrand")
        fl.addWidget(brand)

        parent_layout.addWidget(footer)

    def _pick_ref_image(self, url_input, preview_label, attr_name):
        if not self.api_key:
            QMessageBox.warning(self, "提示", "请先在右上角设置 API Key")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择参考图片",
            os.path.join(os.path.expanduser("~"), "Desktop"),
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)"
        )
        if not path:
            return
        url_input.setText(f"上传中: {os.path.basename(path)} ...")
        url_input.setEnabled(False)

        tag = attr_name
        thread = UploadRefImageThread(self.api_key, path, tag=tag)

        def _on_ok(_tag, url, img_bytes):
            setattr(self, attr_name, url)
            url_input.setEnabled(True)
            url_input.setText(url)
            qimg = QImage.fromData(img_bytes)
            if not qimg.isNull():
                pixmap = QPixmap.fromImage(qimg)
                scaled = pixmap.scaledToHeight(min(pixmap.height(), 150), Qt.SmoothTransformation)
                preview_label.setPixmap(scaled)
            self.footer_status.setText(f"参考图已上传")
            if thread in getattr(self, "_upload_threads", []):
                self._upload_threads.remove(thread)

        def _on_fail(_tag, msg):
            setattr(self, attr_name, None)
            url_input.setEnabled(True)
            url_input.clear()
            preview_label.clear()
            QMessageBox.warning(self, "上传失败", msg)
            if thread in getattr(self, "_upload_threads", []):
                self._upload_threads.remove(thread)

        thread.finished_ok.connect(_on_ok)
        thread.failed.connect(_on_fail)
        if not hasattr(self, "_upload_threads"):
            self._upload_threads = []
        self._upload_threads.append(thread)
        thread.start()

    def _clear_ref_image(self, url_input, preview_label, attr_name):
        setattr(self, attr_name, None)
        url_input.clear()
        preview_label.clear()

    def on_pick_img_ref(self):
        if len(self._img_ref_data_list) >= 4:
            QMessageBox.warning(self, "提示", "最多支持 4 张参考图片")
            return
        if not self.api_key:
            QMessageBox.warning(self, "提示", "请先在右上角设置 API Key")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择参考图片（最多4张）",
            os.path.join(os.path.expanduser("~"), "Desktop"),
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)"
        )
        if not paths:
            return
        slots_left = 4 - len(self._img_ref_data_list)
        paths = paths[:slots_left]
        if not hasattr(self, "_upload_threads"):
            self._upload_threads = []

        for path in paths:
            placeholder = {"url": None, "bytes": None, "name": os.path.basename(path), "uploading": True, "error": None}
            self._img_ref_data_list.append(placeholder)
            tag = f"img_ref_{id(placeholder)}"

            thread = UploadRefImageThread(self.api_key, path, tag=tag)

            def _on_ok(_tag, url, img_bytes, slot=placeholder, th=thread):
                slot["url"] = url
                slot["bytes"] = img_bytes
                slot["uploading"] = False
                self._refresh_img_ref_preview()
                if th in self._upload_threads:
                    self._upload_threads.remove(th)

            def _on_fail(_tag, msg, slot=placeholder, th=thread):
                slot["uploading"] = False
                slot["error"] = msg
                if slot in self._img_ref_data_list:
                    self._img_ref_data_list.remove(slot)
                self._refresh_img_ref_preview()
                QMessageBox.warning(self, "上传失败", f"{slot['name']}: {msg}")
                if th in self._upload_threads:
                    self._upload_threads.remove(th)

            thread.finished_ok.connect(_on_ok)
            thread.failed.connect(_on_fail)
            self._upload_threads.append(thread)
            thread.start()

        self._refresh_img_ref_preview()

    def on_clear_img_ref(self):
        self._img_ref_data_list.clear()
        self._refresh_img_ref_preview()

    def _refresh_img_ref_preview(self):
        while self.img_ref_preview_layout.count():
            w = self.img_ref_preview_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        thumb_size = 90
        for i, slot in enumerate(self._img_ref_data_list):
            img_bytes = slot.get("bytes")
            uploading = slot.get("uploading")
            if img_bytes is None and not uploading:
                continue

            container = QWidget()
            container.setFixedSize(thumb_size + 4, thumb_size + 22)
            container.setStyleSheet("background: transparent;")
            cl = QVBoxLayout(container)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)
            img_lbl = QLabel()
            img_lbl.setFixedSize(thumb_size, thumb_size)
            img_lbl.setAlignment(Qt.AlignCenter)
            img_lbl.setStyleSheet("border: 1px solid rgba(125,211,252,0.3); border-radius: 4px; color:#94a3b8; font-size:11px;")

            if img_bytes:
                qimg = QImage.fromData(img_bytes)
                if not qimg.isNull():
                    pixmap = QPixmap.fromImage(qimg)
                    cropped = pixmap.scaled(thumb_size, thumb_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    x = (cropped.width() - thumb_size) // 2
                    y = (cropped.height() - thumb_size) // 2
                    cropped = cropped.copy(x, y, thumb_size, thumb_size)
                    img_lbl.setPixmap(cropped)
                if uploading:
                    img_lbl.setStyleSheet(img_lbl.styleSheet() + " ")
            else:
                img_lbl.setText("上传中...")
            cl.addWidget(img_lbl, alignment=Qt.AlignCenter)

            del_btn = QPushButton("删除")
            del_btn.setFixedSize(thumb_size, 18)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet("background: rgba(255,107,107,0.2); color: #ff6b6b; border: none; border-radius: 3px; font-size: 10px;")
            del_btn.clicked.connect(lambda checked, x=i: self._remove_img_ref(x))
            cl.addWidget(del_btn, alignment=Qt.AlignCenter)
            row, col = divmod(i, 3)
            self.img_ref_preview_layout.addWidget(container, row, col)
        count = len(self._img_ref_data_list)
        uploading_count = sum(1 for s in self._img_ref_data_list if s.get("uploading"))
        if uploading_count:
            self.img_ref_count_label.setText(f"已选择 {count}/4 张（上传中 {uploading_count}）")
        else:
            self.img_ref_count_label.setText(f"已选择 {count}/4 张" if count > 0 else "")
        self.img_ref_url.setText(f"已选择 {count} 张参考图" if count > 0 else "")

    def _remove_img_ref(self, index):
        if 0 <= index < len(self._img_ref_data_list):
            self._img_ref_data_list.pop(index)
        self._refresh_img_ref_preview()
        if not self._img_ref_data_list:
            self.model_combo.setEnabled(True)

    def on_pick_vid_ref(self):
        self._pick_ref_image(self.vid_ref_url, self.vid_ref_preview, '_vid_ref_data')

    def on_clear_vid_ref(self):
        self._clear_ref_image(self.vid_ref_url, self.vid_ref_preview, '_vid_ref_data')

    def on_model_changed(self, model):
        self.quality_combo.clear()
        qualities = MODEL_QUALITY.get(model, ["1k"])
        self.quality_combo.addItems(qualities)

    def on_generate(self):
        prompt = self.prompt_input.toPlainText().strip()
        print(f"[DEBUG] on_generate called, prompt='{prompt[:50]}', api_key='{self.api_key[:8] if self.api_key else 'NONE'}...'")
        if not prompt:
            QMessageBox.warning(self, "提示", "请输入提示词")
            return
        if any(s.get("uploading") for s in self._img_ref_data_list):
            QMessageBox.warning(self, "提示", "参考图正在上传，请稍候")
            return

        count = int(self.img_count_combo.currentText())
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("生成中...")
        self.save_btn.setEnabled(False)
        self.image_data_list = []
        self._img_done_count = 0
        self._img_total = count
        while self.img_results_layout.count():
            w = self.img_results_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.img_stack.setCurrentIndex(0)
        self._start_search_anim()
        model = self.model_combo.currentText()
        img_ref_urls = [s["url"] for s in self._img_ref_data_list if s.get("url")]
        img_ref = img_ref_urls if img_ref_urls else None
        ratio = self.size_combo.currentText()
        quality = self.quality_combo.currentText()
        actual_size = SIZE_MAP.get(ratio, {}).get(quality, "1024x1024")
        self._current_prompt = prompt
        self._current_model = model
        self._current_quality = quality
        self._current_ratio = ratio
        self.footer_status.setText(f"正在使用 {model} 生成 {count} 张图片 ({ratio} {quality} {actual_size})...")

        self.thread = GenerateThread(
            self.api_key, model, prompt,
            actual_size,
            quality,
            self.format_combo.currentText(),
            count,
            image_url=img_ref
        )
        self.thread.one_finished.connect(self.on_one_image_ready)
        self.thread.error.connect(self.on_img_error)
        self.thread.progress.connect(lambda msg: self.footer_status.setText(msg))
        self.thread.all_done.connect(self.on_all_images_done)
        self.thread.start()

    def on_one_image_ready(self, index, img_bytes):
        self.image_data_list.append(img_bytes)
        self._img_done_count += 1
        self.footer_status.setText(f"已完成 {self._img_done_count}/{self._img_total} 张")

        qimg = QImage.fromData(img_bytes)
        if qimg.isNull():
            return
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        fmt = self.format_combo.currentText()
        ext = fmt if fmt == "png" else "jpg"
        lbl = ClickableLabel(img_bytes, file_ext=ext)
        lbl.setPixmap(scaled)

        cols = 3
        count = self.img_results_layout.count()
        row, col = divmod(count, cols)
        self.img_results_layout.addWidget(lbl, row, col)
        self.img_stack.setCurrentIndex(1)

    def on_img_error(self, index, msg):
        self._img_done_count += 1
        self.footer_status.setText(f"第{index+1}张失败: {msg}")

    def on_all_images_done(self):
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("⚡  生成图片")
        self.save_btn.setEnabled(len(self.image_data_list) > 0)
        total = len(self.image_data_list)
        self.footer_status.setText(f"全部完成，成功 {total}/{self._img_total} 张")
        self._stop_search_anim()
        if self.image_data_list:
            self._save_to_history()

    def _start_search_anim(self):
        if not hasattr(self, "_search_anim_phase"):
            self._search_anim_phase = 0.0
            self._search_timer = QTimer(self)
            self._search_timer.timeout.connect(self._tick_search_anim)
        self._search_anim_phase = 0.0
        self._search_timer.start(33)

    def _stop_search_anim(self):
        if hasattr(self, "_search_timer"):
            self._search_timer.stop()
        if hasattr(self, "img_search_icon") and hasattr(self, "_img_icon_home"):
            hx, hy = self._img_icon_home
            self.img_search_icon.move(hx, hy)
            self._img_icon_opacity.setOpacity(1.0)
        if hasattr(self, "vid_search_icon") and hasattr(self, "_vid_icon_home"):
            hx, hy = self._vid_icon_home
            self.vid_search_icon.move(hx, hy)
            self._vid_icon_opacity.setOpacity(1.0)

    def _tick_search_anim(self):
        period_ms = 2200.0
        self._search_anim_phase += (33.0 / period_ms) * 2 * math.pi
        a = self._search_anim_phase
        radius_x = 30
        radius_y = 14
        x_off = -math.sin(a) * radius_x
        y_off = -(1 - math.cos(a)) * radius_y
        opacity = 0.82 + 0.18 * (1 - abs(math.sin(a)))
        if hasattr(self, "img_search_icon"):
            hx, hy = self._img_icon_home
            self.img_search_icon.move(int(hx + x_off), int(hy + y_off))
            self._img_icon_opacity.setOpacity(opacity)
        if hasattr(self, "vid_search_icon"):
            hx, hy = self._vid_icon_home
            self.vid_search_icon.move(int(hx + x_off), int(hy + y_off))
            self._vid_icon_opacity.setOpacity(opacity)

    def _get_selected_labels(self):
        selected = []
        for i in range(self.img_results_layout.count()):
            w = self.img_results_layout.itemAt(i).widget()
            if w and isinstance(w, ClickableLabel) and w.checked:
                selected.append(w)
        return selected

    def on_select_all_images(self):
        all_checked = True
        for i in range(self.img_results_layout.count()):
            w = self.img_results_layout.itemAt(i).widget()
            if w and isinstance(w, ClickableLabel) and not w.checked:
                all_checked = False
                break
        for i in range(self.img_results_layout.count()):
            w = self.img_results_layout.itemAt(i).widget()
            if w and isinstance(w, ClickableLabel):
                w.checked = not all_checked
                w._update_border()
        self.select_all_btn.setText("取消全选" if not all_checked else "全选")

    def on_save(self):
        selected = self._get_selected_labels()
        if not selected:
            if self.image_data_list:
                QMessageBox.information(self, "提示", "请先单击选中要保存的图片（蓝色边框表示选中）")
            return
        fmt = self.format_combo.currentText()
        ext = fmt if fmt == "png" else "jpg"
        if len(selected) == 1:
            default_name = f"gpt_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
            if fmt == "png":
                filters = "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;所有文件 (*)"
            else:
                filters = "JPEG 图片 (*.jpg);;PNG 图片 (*.png);;所有文件 (*)"
            path, _ = QFileDialog.getSaveFileName(
                self, "保存图片",
                os.path.join(os.path.expanduser("~"), "Desktop", default_name),
                filters
            )
            if path:
                with open(path, "wb") as f:
                    f.write(selected[0].raw_bytes)
                self.footer_status.setText(f"已保存到: {path}")
        else:
            folder = QFileDialog.getExistingDirectory(
                self, "选择保存文件夹",
                os.path.join(os.path.expanduser("~"), "Desktop")
            )
            if folder:
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                for i, lbl in enumerate(selected):
                    path = os.path.join(folder, f"gpt_image_{ts}_{i+1}.{ext}")
                    with open(path, "wb") as f:
                        f.write(lbl.raw_bytes)
                self.footer_status.setText(f"已保存 {len(selected)} 张到: {folder}")

    def on_generate_video(self):
        prompt = self.video_prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "提示", "请输入提示词")
            return

        count = int(self.vid_count_combo.currentText())
        self.video_gen_btn.setEnabled(False)
        self.video_gen_btn.setText("生成中...")
        self.video_save_btn.setEnabled(False)
        self.video_data_list = []
        self._vid_done_count = 0
        self._vid_total = count
        self.vid_placeholder_title.setText("生成中")
        self.vid_placeholder_desc.setText(f"正在生成 {count} 个视频，请耐心等待...")
        self.vid_stack.setCurrentIndex(0)
        while self.vid_results_layout.count():
            w = self.vid_results_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.footer_status.setText(f"正在使用 sora-2 生成 {count} 个视频...")
        self._start_search_anim()

        size_label = self.video_size_combo.currentText()
        size_value = VIDEO_SIZES.get(size_label, "landscape")

        self._current_video_prompt = prompt
        self._current_video_orientation = size_label
        self._current_video_duration = self.video_duration_combo.currentText()

        vid_ref = self._vid_ref_data
        self.video_thread = VideoGenerateThread(
            self.api_key, prompt, size_value,
            self.video_duration_combo.currentText(),
            count,
            image_url=vid_ref
        )
        self.video_thread.one_finished.connect(self.on_one_video_ready)
        self.video_thread.progress.connect(self.on_video_progress)
        self.video_thread.error.connect(self.on_vid_error)
        self.video_thread.all_done.connect(self.on_all_videos_done)
        self.video_thread.start()

    def on_video_progress(self, msg):
        self.video_status_label.setText(msg)
        self.footer_status.setText(msg)

    def on_one_video_ready(self, index, vid_bytes):
        self.video_data_list.append(vid_bytes)
        self._vid_done_count += 1
        size_kb = len(vid_bytes) / 1024
        if size_kb > 1024:
            size_str = f"{size_kb / 1024:.1f} MB"
        else:
            size_str = f"{size_kb:.0f} KB"
        self.footer_status.setText(f"已完成 {self._vid_done_count}/{self._vid_total} 个视频")

        card = ClickableLabel(vid_bytes, file_ext="mp4", is_video=True)
        card.setText(f"🎬\n\n视频 {index+1}\n{size_str}")
        card._vid_style_base = """
            QLabel { border: 2px solid transparent; border-radius: 8px; padding: 8px;
                     background-color: rgba(15, 21, 36, 0.4); color: #a0b4c4; font-size: 13px; }
            QLabel:hover { border-color: rgba(125, 211, 252, 0.3); background-color: rgba(125, 211, 252, 0.05); }
        """
        card._vid_style_checked = """
            QLabel { border: 3px solid #7dd3fc; border-radius: 8px; padding: 8px;
                     background-color: rgba(125, 211, 252, 0.08); color: #a0b4c4; font-size: 13px; }
        """
        card.setStyleSheet(card._vid_style_base)

        cols = 3
        count = self.vid_results_layout.count()
        row, col = divmod(count, cols)
        self.vid_results_layout.addWidget(card, row, col)
        self.vid_stack.setCurrentIndex(1)

    def on_vid_error(self, index, msg):
        self._vid_done_count += 1
        self.footer_status.setText(f"第{index+1}个视频失败: {msg}")

    def on_all_videos_done(self):
        self.video_gen_btn.setEnabled(True)
        self.video_gen_btn.setText("⚡  生成视频")
        self.video_save_btn.setEnabled(len(self.video_data_list) > 0)
        total = len(self.video_data_list)
        if total > 0:
            self.vid_stack.setCurrentIndex(1)
            self._save_videos_to_history()
        self.footer_status.setText(f"全部完成，成功 {total}/{self._vid_total} 个视频")
        self._stop_search_anim()
        self.vid_placeholder_title.setText("等待生成")
        self.vid_placeholder_desc.setText("输入提示词并调整参数，生成高质量 AI 视频")

    def on_select_all_videos(self):
        all_checked = True
        for i in range(self.vid_results_layout.count()):
            w = self.vid_results_layout.itemAt(i).widget()
            if w and isinstance(w, ClickableLabel) and not w.checked:
                all_checked = False
                break
        for i in range(self.vid_results_layout.count()):
            w = self.vid_results_layout.itemAt(i).widget()
            if w and isinstance(w, ClickableLabel):
                w.checked = not all_checked
                w._update_border()
        self.vid_select_all_btn.setText("取消全选" if not all_checked else "全选")

    def on_save_video(self):
        selected = []
        for i in range(self.vid_results_layout.count()):
            w = self.vid_results_layout.itemAt(i).widget()
            if w and isinstance(w, ClickableLabel) and w.checked:
                selected.append(w)
        if not selected:
            if self.video_data_list:
                QMessageBox.information(self, "提示", "请先单击选中要保存的视频（蓝色边框表示选中）")
            return
        if len(selected) == 1:
            default_name = f"sora_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            filters = "MP4 视频 (*.mp4);;所有文件 (*)"
            path, _ = QFileDialog.getSaveFileName(
                self, "保存视频",
                os.path.join(os.path.expanduser("~"), "Desktop", default_name),
                filters
            )
            if path:
                with open(path, "wb") as f:
                    f.write(selected[0].raw_bytes)
                self.footer_status.setText(f"已保存到: {path}")
        else:
            folder = QFileDialog.getExistingDirectory(
                self, "选择保存文件夹",
                os.path.join(os.path.expanduser("~"), "Desktop")
            )
            if folder:
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                for i, lbl in enumerate(selected):
                    path = os.path.join(folder, f"sora_video_{ts}_{i+1}.mp4")
                    with open(path, "wb") as f:
                        f.write(lbl.raw_bytes)
                self.footer_status.setText(f"已保存 {len(selected)} 个视频到: {folder}")

    def _save_to_history(self):
        ensure_history_dir()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        fmt = self.format_combo.currentText()
        ext = fmt if fmt == "png" else "jpg"
        img_paths = []
        for i, data in enumerate(self.image_data_list):
            filename = f"{ts}_{i+1}.{ext}"
            filepath = os.path.join(HISTORY_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(data)
            img_paths.append(filename)
        add_history_record(
            self._current_prompt,
            self._current_model,
            self._current_quality,
            self._current_ratio,
            img_paths
        )

    def _save_videos_to_history(self):
        ensure_history_dir()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        video_paths = []
        for i, data in enumerate(self.video_data_list):
            filename = f"video_{ts}_{i+1}.mp4"
            filepath = os.path.join(HISTORY_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(data)
            video_paths.append(filename)
        add_video_history_record(
            getattr(self, "_current_video_prompt", ""),
            "sora-2",
            getattr(self, "_current_video_orientation", ""),
            getattr(self, "_current_video_duration", ""),
            video_paths,
        )

    def _build_history_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: #0a0e1a;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("生成历史记录")
        title.setObjectName("sectionLabel")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e0e8f0;")
        header.addWidget(title)
        header.addStretch()

        clear_btn = QPushButton("清空历史")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,60,60,0.15); color: #ff6b6b;
                border: 1px solid rgba(255,60,60,0.3); border-radius: 6px;
                padding: 6px 16px; font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,60,60,0.25); }
        """)
        clear_btn.clicked.connect(self._clear_history)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.history_container = QWidget()
        self.history_container.setStyleSheet("background: transparent;")
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setSpacing(12)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.addStretch()

        scroll.setWidget(self.history_container)
        layout.addWidget(scroll)
        self.content_stack.addWidget(page)

    def _refresh_history_page(self):
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        records = load_history()
        if not records:
            empty = QLabel("暂无历史记录")
            empty.setStyleSheet("color: #6b7b8f; font-size: 14px; padding: 40px;")
            empty.setAlignment(Qt.AlignCenter)
            self.history_layout.addWidget(empty)
            self.history_layout.addStretch()
            return

        for record in records:
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background: rgba(255,255,255,0.03);
                    border: 1px solid rgba(255,255,255,0.06);
                    border-radius: 10px;
                }
                QFrame:hover {
                    background: rgba(255,255,255,0.05);
                    border: 1px solid rgba(255,255,255,0.1);
                }
            """)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(12, 12, 12, 12)
            card_layout.setSpacing(12)

            img_container = QHBoxLayout()
            img_container.setSpacing(6)
            thumb_labels = []
            is_video_record = record.get("kind") == "video"
            for img_file in record.get("images", [])[:4]:
                img_path = os.path.join(HISTORY_DIR, img_file)
                if not os.path.exists(img_path):
                    continue
                ext = os.path.splitext(img_file)[1].lstrip(".").lower()
                if is_video_record or ext == "mp4":
                    raw_bytes = open(img_path, "rb").read()
                    lbl = ClickableLabel(raw_bytes, file_ext="mp4", is_video=True)
                    lbl.setText("🎬")
                    lbl.setStyleSheet(
                        "color:#7dd3fc; font-size:32px; background:rgba(125,211,252,0.08);"
                        "border:1px solid rgba(125,211,252,0.3); border-radius:6px;"
                    )
                    lbl.setFixedSize(80, 80)
                    lbl._hist_file = img_file
                    thumb_labels.append(lbl)
                    img_container.addWidget(lbl)
                else:
                    pixmap = QPixmap(img_path)
                    if not pixmap.isNull():
                        raw_bytes = open(img_path, "rb").read()
                        lbl = ClickableLabel(raw_bytes, file_ext=ext)
                        scaled = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        lbl.setPixmap(scaled)
                        lbl.setFixedSize(80, 80)
                        lbl._hist_file = img_file
                        thumb_labels.append(lbl)
                        img_container.addWidget(lbl)
            card_layout.addLayout(img_container)

            info_layout = QVBoxLayout()
            info_layout.setSpacing(4)

            prompt_text = record.get("prompt", "")
            if len(prompt_text) > 80:
                prompt_text = prompt_text[:80] + "..."
            prompt_lbl = QLabel(prompt_text)
            prompt_lbl.setWordWrap(True)
            prompt_lbl.setStyleSheet("color: #e0e8f0; font-size: 12px; border: none;")
            info_layout.addWidget(prompt_lbl)

            unit = "个视频" if is_video_record else "张"
            meta = f"{record.get('time', '')}  |  {record.get('model', '')}  |  {record.get('quality', '')}  |  {record.get('ratio', '')}  |  {len(record.get('images', []))} {unit}"
            meta_lbl = QLabel(meta)
            meta_lbl.setStyleSheet("color: #6b7b8f; font-size: 11px; border: none;")
            info_layout.addWidget(meta_lbl)

            info_layout.addStretch()
            card_layout.addLayout(info_layout, 1)

            dl_btn = QPushButton("下载")
            dl_btn.setCursor(Qt.PointingHandCursor)
            dl_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(125,211,252,0.1); color: #7dd3fc;
                    border: 1px solid rgba(125,211,252,0.3); border-radius: 6px;
                    padding: 8px 16px; font-size: 12px;
                }
                QPushButton:hover { background: rgba(125,211,252,0.2); }
            """)
            img_files = record.get("images", [])
            dl_btn.clicked.connect(lambda checked, files=img_files, labels=thumb_labels: self._download_history_images(files, labels))
            card_layout.addWidget(dl_btn)

            self.history_layout.addWidget(card)

        self.history_layout.addStretch()

    def _download_history_images(self, img_files, labels=None):
        download_files = []
        if labels:
            selected = [lbl._hist_file for lbl in labels if lbl.checked]
            if selected:
                download_files = selected
            else:
                download_files = img_files
        else:
            download_files = img_files

        valid_files = [f for f in download_files if os.path.exists(os.path.join(HISTORY_DIR, f))]
        if not valid_files:
            QMessageBox.warning(self, "提示", "文件已不存在")
            return
        if len(valid_files) == 1:
            src = os.path.join(HISTORY_DIR, valid_files[0])
            ext = os.path.splitext(valid_files[0])[1]
            default_name = f"history_{valid_files[0]}"
            is_video = ext.lower() == ".mp4"
            path, _ = QFileDialog.getSaveFileName(
                self, "保存视频" if is_video else "保存图片",
                os.path.join(os.path.expanduser("~"), "Desktop", default_name),
                f"{'视频文件' if is_video else '图片文件'} (*{ext});;所有文件 (*)"
            )
            if path:
                import shutil
                shutil.copy2(src, path)
                self.footer_status.setText(f"已保存到: {path}")
        else:
            folder = QFileDialog.getExistingDirectory(
                self, "选择保存文件夹",
                os.path.join(os.path.expanduser("~"), "Desktop")
            )
            if folder:
                import shutil
                for f in valid_files:
                    src = os.path.join(HISTORY_DIR, f)
                    shutil.copy2(src, os.path.join(folder, f))
                self.footer_status.setText(f"已保存 {len(valid_files)} 张到: {folder}")

    def _clear_history(self):
        reply = QMessageBox.question(
            self, "确认", "确定要清空所有历史记录吗？图片文件也会被删除。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            import shutil
            if os.path.exists(HISTORY_DIR):
                shutil.rmtree(HISTORY_DIR)
            ensure_history_dir()
            save_history([])
            self._refresh_history_page()
            self.footer_status.setText("历史记录已清空")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))

    dlg = KeyDialog()
    if dlg.exec_() != QDialog.Accepted:
        sys.exit(0)

    window = MainWindow(dlg.get_key())
    window.show()
    sys.exit(app.exec_())
