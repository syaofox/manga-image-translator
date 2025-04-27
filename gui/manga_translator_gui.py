import sys
import os
import json
import subprocess
import threading
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, 
                             QTabWidget, QGroupBox, QTextEdit, QFileDialog, QFrame,
                             QSplitter, QScrollArea)
from PySide6.QtCore import Qt, QThread, Signal

# 默认配置
DEFAULT_CONFIG = {
    "translator": {
        "translator": "sugoi",
        "target_lang": "CHS"
    },
    "detector": {
        "detector": "default"
    },
    "inpainter": {
        "inpainter": "lama_large"
    },
    "render": {
        "renderer": "default",
        "alignment": "auto"
    },
    "ocr": {
        "ocr": "48px"
    }
}

# 支持的语言
LANGUAGES = ["CHS", "CHT", "ENG", "JPN", "KOR", "VIE", "IND", "THA", "RUS", "GER", "FRA", "ITA", "SPA", "POR", "ARA"]

# 翻译器选项
TRANSLATORS = [
    "sugoi", "nllb", "jparacrawl", "m2m100", "mbart50", "chatgpt", "deepl", 
    "baidu", "youdao", "papago", "caiyun", "deepseek", "groq", "gemini", "qwen2", "offline"
]

# 文本检测器选项
DETECTORS = ["default", "dbconvnext", "ctd", "craft", "paddle", "none"]

# 文本擦除器选项
INPAINTERS = ["default", "lama_large", "lama_mpe", "sd", "none", "original"]

# 渲染器选项
RENDERERS = ["default", "manga2eng", "none"]

# 对齐选项
ALIGNMENTS = ["auto", "left", "center", "right"]

# OCR选项
OCRS = ["32px", "48px", "48px_ctc", "mocr"]

def load_config(config_path):
    """加载配置文件"""
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

def save_config(config_path, config):
    """保存配置文件"""
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

class TranslationThread(QThread):
    output_signal = Signal(str)
    complete_signal = Signal(int)
    
    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self.process = None
        self.stopped = False
    
    def run(self):
        self.process = subprocess.Popen(
            self.cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # 读取输出并发送信号
        if self.process and self.process.stdout:
            for line in iter(self.process.stdout.readline, ''):
                if self.stopped:
                    break
                self.output_signal.emit(line.strip())
            
            self.process.stdout.close()
        
        if self.stopped:
            self.output_signal.emit("翻译已被用户中断")
            return_code = -1
        else:
            return_code = self.process.wait()
            
        self.complete_signal.emit(return_code)
    
    def stop(self):
        """停止翻译进程"""
        self.stopped = True
        if self.process:
            self.process.terminate()
            # 给进程一些时间来终止
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # 如果进程没有及时终止，强制终止它
                self.process.kill()

class FormRow(QWidget):
    """创建表单行，包含标签和输入控件"""
    def __init__(self, label_text, input_widget, browse_button=None):
        super().__init__()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel(label_text)
        label.setFixedWidth(100)
        layout.addWidget(label)
        layout.addWidget(input_widget)
        
        if browse_button:
            layout.addWidget(browse_button)
        
        self.setLayout(layout)

class MangaTranslatorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 确定工作目录
        if getattr(sys, 'frozen', False):
            self.application_path = os.path.dirname(sys.executable)
        else:
            self.application_path = os.path.dirname(os.path.abspath(__file__))
            # 向上一级查找项目根目录
            self.application_path = str(Path(self.application_path).parent)
        
        # 配置文件路径
        self.config_path = os.path.join(self.application_path, "config.json")
        
        # 加载配置
        self.config = load_config(self.config_path)
        
        # 初始化UI
        self.setup_ui()
        
        # 翻译线程
        self.translation_thread = None
        
        # 翻译状态
        self.is_translating = False
    
    def setup_ui(self):
        self.setWindowTitle("漫画翻译工具")
        self.setMinimumSize(800, 600)
        
        # 创建中央窗口部件
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # 创建选项卡部件
        self.tabs = QTabWidget()
        
        # 基本设置选项卡
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        
        # 输入目录
        self.input_dir = QLineEdit()
        browse_input = QPushButton("浏览")
        browse_input.clicked.connect(self.browse_input_dir)
        basic_layout.addWidget(FormRow("输入目录:", self.input_dir, browse_input))
        
        # 输出目录
        self.output_dir = QLineEdit()
        browse_output = QPushButton("浏览")
        browse_output.clicked.connect(self.browse_output_dir)
        basic_layout.addWidget(FormRow("输出目录:", self.output_dir, browse_output))
        
        # 目标语言
        self.target_lang = QComboBox()
        self.target_lang.addItems(LANGUAGES)
        if "translator" in self.config and "target_lang" in self.config["translator"]:
            index = self.target_lang.findText(self.config["translator"]["target_lang"])
            if index >= 0:
                self.target_lang.setCurrentIndex(index)
        basic_layout.addWidget(FormRow("目标语言:", self.target_lang))
        
        # 翻译器
        self.translator = QComboBox()
        self.translator.addItems(TRANSLATORS)
        if "translator" in self.config and "translator" in self.config["translator"]:
            index = self.translator.findText(self.config["translator"]["translator"])
            if index >= 0:
                self.translator.setCurrentIndex(index)
        basic_layout.addWidget(FormRow("翻译器:", self.translator))
        
        # 使用GPU
        self.use_gpu = QCheckBox("使用GPU")
        self.use_gpu.setChecked(True)
        basic_layout.addWidget(self.use_gpu)
        
        # 详细输出
        self.verbose = QCheckBox("详细输出")
        self.verbose.setChecked(True)
        basic_layout.addWidget(self.verbose)
        
        basic_layout.addStretch()
        self.tabs.addTab(basic_tab, "基本设置")
        
        # 高级设置选项卡
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        
        # 检测器设置
        detector_group = QGroupBox("文本检测设置")
        detector_layout = QVBoxLayout(detector_group)
        
        self.detector = QComboBox()
        self.detector.addItems(DETECTORS)
        if "detector" in self.config and "detector" in self.config["detector"]:
            index = self.detector.findText(self.config["detector"]["detector"])
            if index >= 0:
                self.detector.setCurrentIndex(index)
        detector_layout.addWidget(FormRow("检测器:", self.detector))
        
        advanced_layout.addWidget(detector_group)
        
        # 擦除器设置
        inpainter_group = QGroupBox("文本擦除设置")
        inpainter_layout = QVBoxLayout(inpainter_group)
        
        self.inpainter = QComboBox()
        self.inpainter.addItems(INPAINTERS)
        if "inpainter" in self.config and "inpainter" in self.config["inpainter"]:
            index = self.inpainter.findText(self.config["inpainter"]["inpainter"])
            if index >= 0:
                self.inpainter.setCurrentIndex(index)
        inpainter_layout.addWidget(FormRow("擦除器:", self.inpainter))
        
        advanced_layout.addWidget(inpainter_group)
        
        # 渲染设置
        render_group = QGroupBox("文本渲染设置")
        render_layout = QVBoxLayout(render_group)
        
        self.renderer = QComboBox()
        self.renderer.addItems(RENDERERS)
        if "render" in self.config and "renderer" in self.config["render"]:
            index = self.renderer.findText(self.config["render"]["renderer"])
            if index >= 0:
                self.renderer.setCurrentIndex(index)
        render_layout.addWidget(FormRow("渲染器:", self.renderer))
        
        self.alignment = QComboBox()
        self.alignment.addItems(ALIGNMENTS)
        if "render" in self.config and "alignment" in self.config["render"]:
            index = self.alignment.findText(self.config["render"]["alignment"])
            if index >= 0:
                self.alignment.setCurrentIndex(index)
        render_layout.addWidget(FormRow("对齐方式:", self.alignment))
        
        advanced_layout.addWidget(render_group)
        
        # OCR设置
        ocr_group = QGroupBox("OCR设置")
        ocr_layout = QVBoxLayout(ocr_group)
        
        self.ocr = QComboBox()
        self.ocr.addItems(OCRS)
        if "ocr" in self.config and "ocr" in self.config["ocr"]:
            index = self.ocr.findText(self.config["ocr"]["ocr"])
            if index >= 0:
                self.ocr.setCurrentIndex(index)
        ocr_layout.addWidget(FormRow("OCR模型:", self.ocr))
        
        advanced_layout.addWidget(ocr_group)
        
        # 其他设置
        other_group = QGroupBox("其他设置")
        other_layout = QVBoxLayout(other_group)
        
        self.ignore_errors = QCheckBox("忽略错误")
        other_layout.addWidget(self.ignore_errors)
        
        self.overwrite = QCheckBox("覆盖已翻译图像")
        other_layout.addWidget(self.overwrite)
        
        self.skip_no_text = QCheckBox("跳过无文本图像")
        other_layout.addWidget(self.skip_no_text)
        
        advanced_layout.addWidget(other_group)
        advanced_layout.addStretch()
        
        self.tabs.addTab(advanced_tab, "高级设置")
        
        main_layout.addWidget(self.tabs)
        
        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(separator)
        
        # 输出文本框
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(200)
        main_layout.addWidget(self.output_text)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("开始翻译")
        self.start_button.clicked.connect(self.toggle_translation)
        button_layout.addWidget(self.start_button)
        
        self.save_config_button = QPushButton("保存配置")
        self.save_config_button.clicked.connect(self.save_configuration)
        button_layout.addWidget(self.save_config_button)
        
        self.exit_button = QPushButton("退出")
        self.exit_button.clicked.connect(self.close)
        button_layout.addWidget(self.exit_button)
        
        main_layout.addLayout(button_layout)
        
        self.setCentralWidget(central_widget)
        
        # 控件列表，用于在翻译期间禁用
        self.input_widgets = [
            self.input_dir, self.output_dir, self.target_lang, self.translator,
            self.use_gpu, self.verbose, self.detector, self.inpainter, self.renderer,
            self.alignment, self.ocr, self.ignore_errors, self.overwrite, self.skip_no_text,
            self.save_config_button, self.tabs
        ]
    
    def browse_input_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输入目录")
        if dir_path:
            self.input_dir.setText(dir_path)
    
    def browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_dir.setText(dir_path)
    
    def save_configuration(self):
        # 更新配置
        if "translator" not in self.config:
            self.config["translator"] = {}
        self.config["translator"]["target_lang"] = self.target_lang.currentText()
        self.config["translator"]["translator"] = self.translator.currentText()
        
        if "detector" not in self.config:
            self.config["detector"] = {}
        self.config["detector"]["detector"] = self.detector.currentText()
        
        if "inpainter" not in self.config:
            self.config["inpainter"] = {}
        self.config["inpainter"]["inpainter"] = self.inpainter.currentText()
        
        if "render" not in self.config:
            self.config["render"] = {}
        self.config["render"]["renderer"] = self.renderer.currentText()
        self.config["render"]["alignment"] = self.alignment.currentText()
        
        if "ocr" not in self.config:
            self.config["ocr"] = {}
        self.config["ocr"]["ocr"] = self.ocr.currentText()
        
        # 保存配置
        save_config(self.config_path, self.config)
        self.output_text.append(f"配置已保存到：{self.config_path}")
    
    def toggle_translation(self):
        """切换翻译状态（开始/停止）"""
        if self.is_translating:
            self.stop_translation()
        else:
            self.start_translation()
    
    def start_translation(self):
        # 检查输入目录
        if not self.input_dir.text():
            self.output_text.append("请选择输入目录！")
            return
        
        # 构建命令
        cmd = ["uv", "run", "python", "-m", "manga_translator", "local", "-i", self.input_dir.text()]
        
        # 添加输出目录（如果有）
        if self.output_dir.text():
            cmd.extend(["-o", self.output_dir.text()])
        
        # 添加详细输出
        if self.verbose.isChecked():
            cmd.append("-v")
        
        # 添加GPU选项
        if self.use_gpu.isChecked():
            cmd.append("--use-gpu")
        
        # 添加配置文件
        cmd.extend(["--config-file", self.config_path])
        
        # 添加高级选项
        if self.ignore_errors.isChecked():
            cmd.append("--ignore-errors")
        if self.overwrite.isChecked():
            cmd.append("--overwrite")
        if self.skip_no_text.isChecked():
            cmd.append("--skip-no-text")
        
        # 更新配置并保存
        self.save_configuration()
        
        # 显示命令
        self.output_text.append("执行命令：" + " ".join(cmd))
        self.output_text.append("开始翻译...\n")
        
        # 禁用界面控件
        self.set_ui_enabled(False)
        
        # 更改按钮文本
        self.start_button.setText("停止翻译")
        self.is_translating = True
        
        # 在线程中运行命令
        self.translation_thread = TranslationThread(cmd)
        self.translation_thread.output_signal.connect(self.update_output)
        self.translation_thread.complete_signal.connect(self.translation_complete)
        self.translation_thread.start()
    
    def stop_translation(self):
        """停止翻译进程"""
        if self.translation_thread and self.translation_thread.isRunning():
            self.output_text.append("正在停止翻译...")
            self.translation_thread.stop()
    
    def set_ui_enabled(self, enabled):
        """启用或禁用界面控件"""
        for widget in self.input_widgets:
            widget.setEnabled(enabled)
    
    def update_output(self, text):
        self.output_text.append(text)
        # 滚动到底部
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )
    
    def translation_complete(self, return_code):
        status = "已完成" if return_code == 0 else "已中断或出错"
        self.output_text.append(f"\n翻译{status}，返回代码：{return_code}")
        
        # 重新启用界面控件
        self.set_ui_enabled(True)
        
        # 恢复按钮文本
        self.start_button.setText("开始翻译")
        self.start_button.setEnabled(True)
        self.is_translating = False

def main():
    app = QApplication(sys.argv)
    window = MangaTranslatorGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 