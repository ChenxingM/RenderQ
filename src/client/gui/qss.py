QSS_THEME = """
/* 全局样式 */
* {
    color: #E0E0E0;
    font-family: "Mi Sans", "MiSans", "微软雅黑", "Segoe UI", Arial;
    font-size: 13px;
}

QToolTip {
    color: #E0E0E0;
    background-color: #2D2D2D;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    padding: 4px 8px;
}

QMainWindow, QWidget {
    background-color: #1E1E1E;
}

QDialog {
    background-color: #1E1E1E;
}

/* 按钮样式 */
QPushButton {
    background-color: #2D2D2D;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    padding: 5px 12px;
    min-height: 24px;
}

QPushButton:hover {
    background-color: #3A3A3A;
    border-color: #4A4A4A;
}

QPushButton:pressed {
    background-color: #252525;
}

QPushButton:disabled {
    color: #666666;
    background-color: #242424;
}

QPushButton:focus {
    border-color: #03A9F4;
}

/* 主要按钮样式 */
QPushButton[primary="true"] {
    background-color: #03A9F4;
    border-color: #03A9F4;
    color: #FFFFFF;
}

QPushButton[primary="true"]:hover {
    background-color: #29B6F6;
    border-color: #29B6F6;
}

QPushButton[primary="true"]:pressed {
    background-color: #0288D1;
}

/* 输入框样式 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #262626;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    padding: 4px 6px;
    min-height: 24px;
    selection-background-color: #03A9F4;
    selection-color: #FFFFFF;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #03A9F4;
    background-color: #2A2A2A;
}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: #666666;
    background-color: #242424;
}

QLineEdit:read-only {
    background-color: #242424;
}

/* 标签样式 */
QLabel {
    padding: 2px;
    background-color: transparent;
}

QLabel:disabled {
    color: #666666;
}

/* 分组框样式 */
QGroupBox {
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
    background-color: transparent;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #B0B0B0;
}

/* 工具栏样式 */
QToolBar {
    background-color: #252525;
    border: none;
    border-bottom: 1px solid #3C3C3C;
    padding: 4px;
    spacing: 4px;
}

QToolBar::separator {
    background-color: #3C3C3C;
    width: 1px;
    margin: 4px 8px;
}

QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}

QToolButton:hover {
    background-color: #3A3A3A;
    border-color: #4A4A4A;
}

QToolButton:pressed {
    background-color: #252525;
}

QToolButton:checked {
    background-color: #03A9F4;
    color: #FFFFFF;
}

/* 列表控件样式 */
QListWidget, QListView {
    background-color: #262626;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    outline: none;
    alternate-background-color: #2A2A2A;
}

QListWidget::item, QListView::item {
    padding: 4px 8px;
    background-color: transparent;
    border-radius: 2px;
}

QListWidget::item:alternate, QListView::item:alternate {
    background-color: #2A2A2A;
}

QListWidget::item:hover, QListView::item:hover {
    background-color: #3A3A3A;
}

QListWidget::item:selected, QListView::item:selected {
    background-color: #03A9F4;
    color: #FFFFFF;
}

/* Tab控件样式 */
QTabWidget::pane {
    background-color: #262626;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    top: -1px;
}

QTabWidget::tab-bar {
    left: 0px;
}

QTabBar::tab {
    background-color: #2D2D2D;
    color: #B0B0B0;
    border: 1px solid #3C3C3C;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 16px;
    margin-right: 2px;
    min-width: 60px;
}

QTabBar::tab:hover {
    background-color: #3A3A3A;
    color: #E0E0E0;
}

QTabBar::tab:selected {
    background-color: #03A9F4;
    color: #FFFFFF;
    font-weight: bold;
    border-color: #03A9F4;
}

QTabBar::tab:!selected {
    margin-top: 2px;
}

/* 菜单样式 */
QMenuBar {
    background-color: #2D2D2D;
    border-bottom: 1px solid #3C3C3C;
    padding: 2px;
}

QMenuBar::item {
    background-color: transparent;
    padding: 4px 8px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #3A3A3A;
}

QMenu {
    background-color: #2D2D2D;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #03A9F4;
    color: #FFFFFF;
}

QMenu::item:disabled {
    color: #666666;
}

QMenu::separator {
    height: 1px;
    background-color: #3C3C3C;
    margin: 4px 8px;
}

QMenu::indicator {
    width: 16px;
    height: 16px;
    margin-left: 4px;
}

/* 状态栏样式 */
QStatusBar {
    background-color: #252525;
    border-top: 1px solid #3C3C3C;
    padding: 2px;
}

QStatusBar::item {
    border: none;
}

/* 复选框样式 */
QCheckBox {
    spacing: 8px;
    background-color: transparent;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #3C3C3C;
    border-radius: 3px;
    background-color: #262626;
}

QCheckBox::indicator:hover {
    border-color: #03A9F4;
}

QCheckBox::indicator:checked {
    background-color: #03A9F4;
    border-color: #03A9F4;
    image: url(:/icons/check.png);
}

QCheckBox::indicator:disabled {
    background-color: #242424;
    border-color: #333333;
}

/* 单选按钮样式 */
QRadioButton {
    spacing: 8px;
    background-color: transparent;
}

QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #3C3C3C;
    border-radius: 9px;
    background-color: #262626;
}

QRadioButton::indicator:hover {
    border-color: #03A9F4;
}

QRadioButton::indicator:checked {
    background-color: #03A9F4;
    border-color: #03A9F4;
}

QRadioButton::indicator:disabled {
    background-color: #242424;
    border-color: #333333;
}

/* 分割器样式 */
QSplitter::handle {
    background-color: #2D2D2D;
}

QSplitter::handle:horizontal {
    width: 4px;
}

QSplitter::handle:vertical {
    height: 4px;
}

QSplitter::handle:hover {
    background-color: #03A9F4;
}

/* 表格控件样式 */
QTableWidget, QTableView {
    background-color: #262626;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    outline: none;
    alternate-background-color: #2A2A2A;
    gridline-color: #3C3C3C;
    selection-background-color: #03A9F4;
    selection-color: #FFFFFF;
}

QTableWidget::item, QTableView::item {
    padding: 4px 8px;
    background-color: transparent;
}

QTableWidget::item:alternate, QTableView::item:alternate {
    background-color: #2A2A2A;
}

QTableWidget::item:hover, QTableView::item:hover {
    background-color: #3A3A3A;
}

QTableWidget::item:selected, QTableView::item:selected {
    background-color: #03A9F4;
    color: #FFFFFF;
}

/* 树控件样式 */
QTreeWidget, QTreeView {
    background-color: #262626;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    outline: none;
    alternate-background-color: #2A2A2A;
}

QTreeWidget::item, QTreeView::item {
    padding: 4px;
    background-color: transparent;
}

QTreeWidget::item:alternate, QTreeView::item:alternate {
    background-color: #2A2A2A;
}

QTreeWidget::item:hover, QTreeView::item:hover {
    background-color: #3A3A3A;
}

QTreeWidget::item:selected, QTreeView::item:selected {
    background-color: #03A9F4;
    color: #FFFFFF;
}

QTreeWidget::branch:has-siblings:!adjoins-item {
    border-image: none;
}

QTreeWidget::branch:has-siblings:adjoins-item {
    border-image: none;
}

QTreeWidget::branch:!has-children:!has-siblings:adjoins-item {
    border-image: none;
}

/* 表头样式 */
QHeaderView {
    background-color: transparent;
    border: none;
}

QHeaderView::section {
    background-color: #2D2D2D;
    border: none;
    border-right: 1px solid #3C3C3C;
    border-bottom: 1px solid #3C3C3C;
    padding: 6px 8px;
    font-weight: bold;
    color: #B0B0B0;
}

QHeaderView::section:hover {
    background-color: #3A3A3A;
    color: #E0E0E0;
}

QHeaderView::section:pressed {
    background-color: #03A9F4;
    color: #FFFFFF;
}

/* 文本编辑框样式 */
QTextEdit, QPlainTextEdit {
    background-color: #262626;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    padding: 4px;
    selection-background-color: #03A9F4;
    selection-color: #FFFFFF;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #03A9F4;
}

/* 进度条样式 */
QProgressBar {
    background-color: #262626;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    text-align: center;
    color: #E0E0E0;
    height: 20px;
}

QProgressBar::chunk {
    background-color: #03A9F4;
    border-radius: 3px;
}

/* 滑块样式 */
QSlider::groove:horizontal {
    background-color: #262626;
    border: 1px solid #3C3C3C;
    height: 6px;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background-color: #03A9F4;
    border: none;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background-color: #29B6F6;
}

QSlider::groove:vertical {
    background-color: #262626;
    border: 1px solid #3C3C3C;
    width: 6px;
    border-radius: 3px;
}

QSlider::handle:vertical {
    background-color: #03A9F4;
    border: none;
    width: 16px;
    height: 16px;
    margin: 0 -5px;
    border-radius: 8px;
}

QSlider::handle:vertical:hover {
    background-color: #29B6F6;
}

/* 滚动条样式 */
QScrollBar:vertical {
    background-color: #1E1E1E;
    width: 12px;
    border-radius: 6px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #3C3C3C;
    min-height: 30px;
    border-radius: 6px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #4A4A4A;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background-color: transparent;
}

QScrollBar:horizontal {
    background-color: #1E1E1E;
    height: 12px;
    border-radius: 6px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #3C3C3C;
    min-width: 30px;
    border-radius: 6px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #4A4A4A;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background-color: transparent;
}

/* SpinBox按钮样式 */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #2D2D2D;
    border: none;
    border-left: 1px solid #3C3C3C;
    width: 20px;
}

QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #03A9F4;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 6px solid #B0B0B0;
}

QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {
    border-bottom-color: #FFFFFF;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #B0B0B0;
}

QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {
    border-top-color: #FFFFFF;
}

/* ComboBox下拉按钮样式 */
QComboBox::drop-down {
    border: none;
    border-left: 1px solid #3C3C3C;
    width: 24px;
    background-color: transparent;
}

QComboBox::drop-down:hover {
    background-color: #03A9F4;
}

QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #B0B0B0;
}

QComboBox::down-arrow:hover {
    border-top-color: #FFFFFF;
}

QComboBox::down-arrow:on {
    border-top: none;
    border-bottom: 6px solid #B0B0B0;
}

QComboBox QAbstractItemView {
    background-color: #2D2D2D;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    selection-background-color: #03A9F4;
    selection-color: #FFFFFF;
    outline: none;
    padding: 4px;
}

QComboBox QAbstractItemView::item {
    padding: 6px 8px;
    border-radius: 4px;
}

QComboBox QAbstractItemView::item:hover {
    background-color: #3A3A3A;
}

QComboBox QAbstractItemView::item:selected {
    background-color: #03A9F4;
    color: #FFFFFF;
}

/* 对话框按钮样式 */
QDialogButtonBox QPushButton {
    min-width: 80px;
}

/* 消息框样式 */
QMessageBox {
    background-color: #1E1E1E;
}

QMessageBox QLabel {
    color: #E0E0E0;
}

/* 输入对话框样式 */
QInputDialog {
    background-color: #1E1E1E;
}

/* Frame样式 */
QFrame[frameShape="4"], /* HLine */
QFrame[frameShape="5"]  /* VLine */ {
    background-color: #3C3C3C;
}

/* 日期时间编辑框 */
QDateEdit, QTimeEdit, QDateTimeEdit {
    background-color: #262626;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    padding: 4px 6px;
    min-height: 24px;
}

QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {
    border-color: #03A9F4;
}

QDateEdit::drop-down, QTimeEdit::drop-down, QDateTimeEdit::drop-down {
    border: none;
    border-left: 1px solid #3C3C3C;
    width: 24px;
}

QCalendarWidget {
    background-color: #2D2D2D;
}

QCalendarWidget QToolButton {
    color: #E0E0E0;
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px;
}

QCalendarWidget QToolButton:hover {
    background-color: #3A3A3A;
}

QCalendarWidget QMenu {
    background-color: #2D2D2D;
}

QCalendarWidget QSpinBox {
    background-color: #262626;
}

QCalendarWidget QWidget#qt_calendar_navigationbar {
    background-color: #2D2D2D;
}

QCalendarWidget QTableView {
    background-color: #262626;
    selection-background-color: #03A9F4;
    selection-color: #FFFFFF;
}

/* 停靠窗口样式 */
QDockWidget {
    background-color: #1E1E1E;
    titlebar-close-icon: url(:/icons/close.png);
    titlebar-normal-icon: url(:/icons/float.png);
}

QDockWidget::title {
    background-color: #2D2D2D;
    padding: 6px;
    border-bottom: 1px solid #3C3C3C;
}

QDockWidget::close-button, QDockWidget::float-button {
    background-color: transparent;
    border: none;
    padding: 2px;
}

QDockWidget::close-button:hover, QDockWidget::float-button:hover {
    background-color: #3A3A3A;
}
"""
