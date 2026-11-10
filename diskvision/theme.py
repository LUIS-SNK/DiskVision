def stylesheet(dark):
    bg, panel, raised, text, muted, border = (
        ("#0d1524", "#131f32", "#1a2a42", "#e9f0fa", "#a6bad2", "#293d58")
        if dark else ("#edf2f8", "#ffffff", "#e6eef8", "#13243e", "#465d7a", "#c7d5e5")
    )
    return f"""
    QWidget {{ background: {bg}; color: {text}; font: 10pt 'Segoe UI'; }}
    QFrame#sidebar, QFrame#toolbar {{ background: {panel}; border: 1px solid {border}; border-radius: 10px; }}
    QLabel {{ background: transparent; }}
    QLabel#brand {{ font-size: 20pt; font-weight: 700; }}
    QLabel#title {{ font-size: 22pt; font-weight: 700; }}
    QLabel#eyebrow {{ color: {muted}; font-size: 9pt; font-weight: 700; }}
    QLabel#muted {{ color: {muted}; }}
    QPushButton, QComboBox, QSpinBox {{ background: {raised}; border: 1px solid {border};
        border-radius: 7px; min-height: 27px; padding: 4px 10px; }}
    QPushButton:hover, QPushButton:checked {{ border-color: #4294f0; }}
    QPushButton:checked {{ background: #215a9e; color: white; }}
    QPushButton#primary {{ background: #2368bf; color: white; border-color: #357fd8; font-weight: 600; }}
    QPushButton#danger {{ color: #ffffff; background: #8e3047; border-color: #aa4860; }}
    QPushButton:disabled, QComboBox:disabled {{ color: {muted}; background: {panel}; border-color: {border}; }}
    QTableView {{ background: {panel}; alternate-background-color: {raised}; border: 1px solid {border};
        border-radius: 7px; gridline-color: {border}; selection-background-color: #245a99; selection-color: white; }}
    QHeaderView::section {{ background: {raised}; color: {text}; padding: 7px;
        border: 0; border-bottom: 1px solid {border}; }}
    QProgressBar {{ background: {raised}; border: 1px solid {border}; border-radius: 5px; text-align: center; }}
    QProgressBar::chunk {{ background: #347ed1; border-radius: 4px; }}
    QScrollArea {{ border: 0; }}
    """
