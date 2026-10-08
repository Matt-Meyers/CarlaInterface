from PyQt6.QtGui import QPalette, QColor, QColorConstants


def set_full_dark():
    """Set darkmode palette for PyQt6"""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.WindowText, QColorConstants.White)
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColorConstants.White)
    palette.setColor(QPalette.ColorRole.ToolTipText, QColorConstants.White)
    palette.setColor(QPalette.ColorRole.Text, QColorConstants.White)
    palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 55))
    palette.setColor(QPalette.ColorRole.ButtonText, QColorConstants.White)
    palette.setColor(QPalette.ColorRole.BrightText, QColorConstants.Red)
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColorConstants.Black)

    return palette


def set_active(palette):
    """Adjust palette for active item"""
    palette.setColor(QPalette.ColorRole.Button, QColor(23, 23, 23))
    palette.setColor(QPalette.ColorRole.ButtonText, QColorConstants.White)
    return palette


def set_alt_active(palette):
    """Adjust palette for alt-active item"""
    # palette.setColor(QPalette.ColorRole.Button, QColor(15, 15, 40))
    palette.setColor(QPalette.ColorRole.Button, QColor(20, 20, 60))
    palette.setColor(QPalette.ColorRole.ButtonText, QColorConstants.White)
    return palette

