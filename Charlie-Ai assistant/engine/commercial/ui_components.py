"""
engine/commercial/ui_components.py — PyQt6 UI Overlays for Pricing, Subscription Management, and Paywall Modals.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtGui import QColor, QFont, QPainter
    from PyQt6.QtWidgets import (
        QDialog,
        QFrame,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

from .core import CommercialEngine, get_commercial_engine
from .models import PlanTier


class PricingOverlay(QFrame if PYQT_AVAILABLE else object):
    """Full-screen modern Pricing Catalog and Feature Comparison Table."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        engine: Optional[CommercialEngine] = None,
        on_select_plan: Optional[Callable[[PlanTier], None]] = None,
        forced_paywall: bool = False,
    ):
        if not PYQT_AVAILABLE:
            return
        super().__init__(parent)
        self.engine = engine or get_commercial_engine()
        self.on_select_plan = on_select_plan
        self.forced_paywall = forced_paywall
        self.setObjectName("pricingOverlay")
        self.setStyleSheet("""
            #pricingOverlay {
                background: rgba(10, 13, 20, 0.98);
                border: none;
            }
            #pricingOverlay QLabel {
                border: none;
                background: transparent;
            }
            #closeBtn {
                background: #1e2430;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            #closeBtn:hover {
                background: #283344;
                color: #f8fafc;
                border-color: #8aa4ff;
            }
        """)
        self._init_ui()
        if parent:
            self.setGeometry(0, 0, parent.width(), parent.height())

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            self.setGeometry(0, 0, self.parent().width(), self.parent().height())

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 20, 28, 20)
        main_layout.setSpacing(14)

        # Header Row
        header_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)

        if self.forced_paywall:
            banner = QLabel("⚠️ DAILY 10-MINUTE FREE STARTER ALLOWANCE EXHAUSTED")
            banner.setStyleSheet("""
                color: #ff4d6d;
                background: #2b1118;
                border: 1px solid #ef4444;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 0.8px;
            """)
            title_box.addWidget(banner)

        title = QLabel("Choose the CHARLIE that fits your workflow")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #f8fafc; font-size: 22px; font-weight: 700;")
        title_box.addWidget(title)

        sub_text = (
            "Your 10 free daily minutes are complete. Assistant commands and microphone are paused.\n"
            "Select a plan below to activate uninterrupted CHARLIE access immediately."
            if self.forced_paywall
            else "Start free. Upgrade anytime to unlock more voices, proactive intelligence and full system automation."
        )
        subtitle = QLabel(sub_text)
        subtitle.setStyleSheet("color: #94a3b8; font-size: 13px; line-height: 1.4;")
        title_box.addWidget(subtitle)
        header_row.addLayout(title_box)

        header_row.addStretch()

        close_txt = "✕ Close (Assistant Paused)" if self.forced_paywall else "✕ Close"
        close_btn = QPushButton(close_txt)
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedHeight(34)
        if self.forced_paywall:
            close_btn.setMinimumWidth(180)
        else:
            close_btn.setFixedWidth(86)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        header_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        main_layout.addLayout(header_row)

        # Scrollable Content (Cards + Comparison Table)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 6, 0, 16)
        content_layout.setSpacing(22)

        # 1. Pricing Cards Row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)

        current_plan = self.engine.get_account().plan
        # Only show lifetime card if user already has legacy lifetime
        if current_plan == PlanTier.LIFETIME:
            plans = self.engine.plan_registry.list_plans()
        else:
            plans = self.engine.plan_registry.list_public_plans()

        for p in plans:
            card = self._create_plan_card(p, is_current=(p.tier == current_plan))
            cards_row.addWidget(card)

        content_layout.addLayout(cards_row)

        # 2. Detailed Feature Comparison Table
        table_label = QLabel("Detailed Feature Comparison")
        table_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        table_label.setStyleSheet("color: #8aa4ff; margin-top: 8px; font-size: 16px;")
        content_layout.addWidget(table_label)

        table = self._create_comparison_table()
        content_layout.addWidget(table)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _create_plan_card(self, plan: Any, is_current: bool = False) -> QFrame:
        card = QFrame()
        card_id = f"card_{plan.tier.value}"
        card.setObjectName(card_id)
        card.setMinimumWidth(200)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        is_popular = (plan.badge == "MOST POPULAR")
        is_annual = (plan.tier == PlanTier.ANNUAL_PRO)
        is_pro_plus = (plan.tier == PlanTier.PRO_PLUS)
        is_lifetime = (plan.tier == PlanTier.LIFETIME)

        if is_popular:
            border_col = "#6366f1"
            bg_col = "#151c2c"
            border_w = "2px"
        elif is_annual:
            border_col = "#06b6d4"
            bg_col = "#0e1a26"
            border_w = "2px"
        elif is_pro_plus:
            border_col = "#10b981"
            bg_col = "#0e1d20"
            border_w = "1px"
        elif is_lifetime:
            border_col = "#f59e0b"
            bg_col = "#1f1910"
            border_w = "1px"
        else:
            border_col = "#222c3d"
            bg_col = "#111622"
            border_w = "1px"

        card.setStyleSheet(f"""
            QFrame#{card_id} {{
                background: {bg_col};
                border: {border_w} solid {border_col};
                border-radius: 12px;
                padding: 16px 12px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Badge row
        if plan.badge:
            badge = QLabel(plan.badge)
            if is_popular:
                badge_bg = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #8aa4ff)"
                badge_color = "#ffffff"
            elif is_annual:
                badge_bg = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #3b82f6)"
                badge_color = "#ffffff"
            elif is_pro_plus:
                badge_bg = "#10b981"
                badge_color = "#ffffff"
            elif is_lifetime:
                badge_bg = "#f59e0b"
                badge_color = "#0f172a"
            else:
                badge_bg = "#334155"
                badge_color = "#f1f5f9"

            badge.setStyleSheet(f"""
                background: {badge_bg};
                color: {badge_color};
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.5px;
                border-radius: 4px;
                padding: 3px 8px;
            """)
            badge.setFixedHeight(22)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(badge)
        else:
            spacer = QLabel("")
            spacer.setFixedHeight(22)
            layout.addWidget(spacer)

        # Plan Name
        name_lbl = QLabel(plan.name.upper())
        name_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        name_lbl.setStyleSheet("color: #f1f5f9; letter-spacing: 0.5px;")
        layout.addWidget(name_lbl)

        # Price
        if plan.tier == PlanTier.ANNUAL_PRO:
            price_html = (
                "<span style='font-size: 24px; font-weight: 800; color: #ffffff;'>₹2,999</span>"
                " <span style='font-size: 12px; color: #94a3b8; font-weight: 500;'>/yr</span><br/>"
                "<span style='font-size: 11px; text-decoration: line-through; color: #64748b;'>₹3,588</span> "
                "<span style='font-size: 11px; color: #10b981; font-weight: 700;'>Save ₹589 (~16.4%)</span>"
            )
        else:
            price_val = f"₹{plan.price_inr}" if plan.price_inr > 0 else "FREE"
            cycle_txt = "/mo" if plan.is_recurring else (" one-time" if plan.price_inr > 0 else "")
            price_html = f"<span style='font-size: 24px; font-weight: 800; color: #ffffff;'>{price_val}</span>"
            if cycle_txt:
                price_html += f" <span style='font-size: 12px; color: #94a3b8; font-weight: 500;'>{cycle_txt}</span>"
        price_lbl = QLabel(price_html)
        price_lbl.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(price_lbl)

        # Tagline
        tagline_lbl = QLabel(plan.tagline)
        tagline_lbl.setStyleSheet("color: #8aa4ff; font-size: 11px; font-weight: 600;")
        layout.addWidget(tagline_lbl)

        # Separator line
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #252e3d; border: none; margin: 4px 0;")
        layout.addWidget(sep)

        # Benefits List (No boxes, clean list)
        for b in plan.benefits[:6]:
            b_lbl = QLabel(f"<span style='color: #34d399; font-weight: bold;'>✓</span> {b}")
            b_lbl.setTextFormat(Qt.TextFormat.RichText)
            b_lbl.setWordWrap(True)
            b_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px; line-height: 1.3;")
            layout.addWidget(b_lbl)

        layout.addStretch()

        # Action Button
        if is_current:
            btn = QPushButton("✓ Current Plan")
            btn.setEnabled(False)
            btn.setFixedHeight(36)
            btn.setStyleSheet("""
                QPushButton {
                    background: #1e2533;
                    color: #64748b;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    font-weight: 600;
                    font-size: 12px;
                }
            """)
        else:
            action_text = "Start Free" if plan.tier == PlanTier.STARTER else f"Get {plan.name}"
            btn = QPushButton(action_text)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if is_popular:
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #8aa4ff);
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        font-weight: 700;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7579ff, stop:1 #9bb0ff);
                    }
                """)
            elif is_annual:
                btn.setStyleSheet("""
                    QPushButton {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:1 #3b82f6);
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        font-weight: 800;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0891b2, stop:1 #2563eb);
                    }
                """)
            elif is_lifetime:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #f59e0b;
                        color: #0f172a;
                        border: none;
                        border-radius: 6px;
                        font-weight: 800;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background: #fbbf24;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #1e2638;
                        color: #e2e8f0;
                        border: 1px solid #3b485d;
                        border-radius: 6px;
                        font-weight: 600;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background: #2a3449;
                        border-color: #8aa4ff;
                        color: #ffffff;
                    }
                """)
            btn.clicked.connect(lambda _, t=plan.tier: self._on_plan_clicked(t))

        layout.addWidget(btn)
        return card

    def _create_comparison_table(self) -> QTableWidget:
        rows = self.engine.pricing_ui_mgr.get_comparison_table()
        table = QTableWidget(len(rows), 6)
        table.setHorizontalHeaderLabels(["Feature", "Starter", "Basic", "Pro", "Pro+", "Annual Pro"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)
        table.setStyleSheet("""
            QTableWidget {
                background: #111622;
                color: #e2e8f0;
                gridline-color: #1a2233;
                border: 1px solid #222d3d;
                border-radius: 8px;
                font-size: 11px;
            }
            QHeaderView::section {
                background: #182030;
                color: #8aa4ff;
                font-weight: 700;
                border: 1px solid #222d3d;
                padding: 6px;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #1a2233;
            }
        """)

        for i, row in enumerate(rows):
            f_item = QTableWidgetItem(str(row["feature"]))
            f_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(i, 0, f_item)

            for col_idx, col_key in enumerate(["starter", "basic", "pro", "pro_plus", "annual_pro"], 1):
                val = str(row[col_key])
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if val == "✓":
                    item.setForeground(QColor("#34d399"))
                elif val == "—":
                    item.setForeground(QColor("#64748b"))
                table.setItem(i, col_idx, item)

        table.setFixedHeight(480)
        return table

    def _on_plan_clicked(self, tier: PlanTier) -> None:
        if self.on_select_plan:
            self.on_select_plan(tier)


class PaywallModal(QDialog if PYQT_AVAILABLE else object):
    """Modal dialog displayed when Starter 10-minute allowance is exhausted."""

    def __init__(self, parent: Optional[QWidget] = None, on_upgrade: Optional[Callable[[], None]] = None):
        if not PYQT_AVAILABLE:
            return
        super().__init__(parent)
        self.on_upgrade = on_upgrade
        self.setWindowTitle("Daily Free Allowance Complete")
        self.setFixedSize(480, 260)
        self.setStyleSheet("""
            QDialog {
                background: #171a21;
                border: 1px solid #525c6c;
                border-radius: 8px;
            }
            QLabel { color: #dce3ed; }
            QPushButton {
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton#primaryBtn {
                background: #8aa4ff;
                color: #12151b;
                border: 1px solid #8aa4ff;
            }
            QPushButton#secondaryBtn {
                background: #282d38;
                color: #dce3ed;
                border: 1px solid #3a414e;
            }
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Today's free CHARLIE time is complete.")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        msg = QLabel(
            "You've used your 10 free minutes for today.\n"
            "Upgrade for uninterrupted CHARLIE access, or continue tomorrow when your free allowance resets."
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #98a4b5; font-size: 12px; line-height: 1.4;")
        layout.addWidget(msg)

        note = QLabel("Your personal data, memories, and files remain completely safe and accessible.")
        note.setStyleSheet("color: #34d399; font-size: 11px;")
        layout.addWidget(note)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        later_btn = QPushButton("Come Back Tomorrow")
        later_btn.setObjectName("secondaryBtn")
        later_btn.clicked.connect(self.accept)
        btn_row.addWidget(later_btn)

        upgrade_btn = QPushButton("Upgrade Now")
        upgrade_btn.setObjectName("primaryBtn")
        upgrade_btn.clicked.connect(self._handle_upgrade)
        btn_row.addWidget(upgrade_btn)

        layout.addLayout(btn_row)

    def _handle_upgrade(self) -> None:
        self.accept()
        if self.on_upgrade:
            self.on_upgrade()


class StarterUsageIndicatorWidget(QFrame if PYQT_AVAILABLE else object):
    """Header widget showing active Starter time remaining."""

    def __init__(self, parent: Optional[QWidget] = None, engine: Optional[CommercialEngine] = None, on_click: Optional[Callable[[], None]] = None):
        if not PYQT_AVAILABLE:
            return
        super().__init__(parent)
        self.engine = engine or get_commercial_engine()
        self.on_click = on_click
        self.setFixedHeight(26)
        self.setStyleSheet("""
            StarterUsageIndicatorWidget {
                background: #20242d;
                border: 1px solid #3a414e;
                border-radius: 4px;
                padding: 2px 8px;
            }
            QLabel { color: #bbc5d3; font-size: 11px; }
            QPushButton {
                background: transparent;
                color: #8aa4ff;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { text-decoration: underline; }
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(8)

        self.label = QLabel("Starter · 10:00 left")
        layout.addWidget(self.label)

        self.upgrade_btn = QPushButton("Upgrade")
        self.upgrade_btn.clicked.connect(self._on_btn_clicked)
        layout.addWidget(self.upgrade_btn)

        self.refresh()

    def refresh(self) -> None:
        status = self.engine.get_starter_time_status()
        if not status["is_starter"]:
            self.label.setText(status["label"])
            self.upgrade_btn.setText("Manage")
        else:
            self.label.setText(status["label"])
            self.upgrade_btn.setText("Upgrade")

    def _on_btn_clicked(self) -> None:
        if self.on_click:
            self.on_click()


class AutoUpdateDialog(QDialog if PYQT_AVAILABLE else object):
    """Clean modern modal showing update availability, release notes, and action buttons."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        update_info: Optional[Dict[str, Any]] = None,
        on_update_now: Optional[Callable[[], None]] = None,
        on_install_later: Optional[Callable[[], None]] = None,
    ):
        if not PYQT_AVAILABLE:
            return
        super().__init__(parent)
        self.update_info = update_info or {}
        self.on_update_now = on_update_now
        self.on_install_later = on_install_later
        self.setWindowTitle("CHARLIE Software Update Available")
        self.setFixedSize(520, 420)
        self.setStyleSheet("""
            QDialog {
                background: #12141a;
                color: #e6edf3;
            }
            QLabel { color: #e6edf3; }
            #title { font-size: 18px; font-weight: bold; color: #58a6ff; }
            #versionTag { font-size: 13px; color: #7ee787; font-weight: bold; }
            #notesArea {
                background: #1c2128;
                border: 1px solid #30363d;
                border-radius: 6px;
                color: #c9d1d9;
                padding: 12px;
                font-family: monospace;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }
            #primaryBtn {
                background: #238636;
                color: white;
                border: 1px solid #2ea043;
            }
            #primaryBtn:hover { background: #2ea043; }
            #secondaryBtn {
                background: #21262d;
                color: #c9d1d9;
                border: 1px solid #30363d;
            }
            #secondaryBtn:hover { background: #30363d; }
        """)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("New Update Available")
        title.setObjectName("title")
        layout.addWidget(title)

        ver = self.update_info.get("latest_version", "1.0.1")
        channel = self.update_info.get("channel", "STABLE")
        size_mb = round(self.update_info.get("file_size", 0) / (1024 * 1024), 1) or 151.0
        sec_str = " · Security Update" if self.update_info.get("security_update") else ""

        ver_label = QLabel(f"CHARLIE v{ver} ({channel}{sec_str}) · {size_mb} MB")
        ver_label.setObjectName("versionTag")
        layout.addWidget(ver_label)

        notes_label = QLabel("Release Notes:")
        notes_label.setStyleSheet("font-weight: bold; color: #8b949e;")
        layout.addWidget(notes_label)

        notes_content = self.update_info.get("release_notes") or "Performance improvements, security hardening, and bug fixes."
        notes_scroll = QScrollArea()
        notes_scroll.setWidgetResizable(True)
        notes_widget = QLabel(notes_content)
        notes_widget.setObjectName("notesArea")
        notes_widget.setWordWrap(True)
        notes_scroll.setWidget(notes_widget)
        layout.addWidget(notes_scroll)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        later_btn = QPushButton("Install Later")
        later_btn.setObjectName("secondaryBtn")
        later_btn.clicked.connect(self._handle_later)
        btn_row.addWidget(later_btn)

        update_btn = QPushButton("Update Now")
        update_btn.setObjectName("primaryBtn")
        update_btn.clicked.connect(self._handle_now)
        btn_row.addWidget(update_btn)

        layout.addLayout(btn_row)

    def _handle_now(self) -> None:
        self.accept()
        if self.on_update_now:
            self.on_update_now()

    def _handle_later(self) -> None:
        self.reject()
        if self.on_install_later:
            self.on_install_later()


class CrashRecoveryDialog(QDialog if PYQT_AVAILABLE else object):
    """Post-crash recovery dialog shown on restart."""

    def __init__(
        self,
        crash_id: str,
        error_summary: str = "",
        parent: Optional[QWidget] = None,
        on_send_report: Optional[Callable[[bool], None]] = None,
        on_report_problem: Optional[Callable[[], None]] = None,
    ):
        if not PYQT_AVAILABLE:
            return
        super().__init__(parent)
        self.crash_id = crash_id
        self.error_summary = error_summary
        self.on_send_report = on_send_report
        self.on_report_problem = on_report_problem
        self.setWindowTitle("CHARLIE Crash Recovery")
        self.setFixedSize(520, 360)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("⚠️ CHARLIE recovered from an unexpected error.")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f85149;")
        layout.addWidget(title)

        ref_box = QLabel(f"Crash Reference: <b>{self.crash_id}</b>")
        ref_box.setStyleSheet("background: #161b22; border: 1px solid #30363d; padding: 8px; border-radius: 6px; color: #58a6ff;")
        layout.addWidget(ref_box)

        desc = QLabel(
            "A diagnostic report can help our engineering team identify and fix this issue. "
            "Reports are strictly technical and never contain user documents, code, memory, or passwords."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8b949e; font-size: 13px;")
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        send_btn = QPushButton("Send Diagnostic Report")
        send_btn.setStyleSheet("background: #238636; color: white; padding: 8px 14px; border-radius: 6px; font-weight: bold;")
        send_btn.clicked.connect(self._handle_send)
        btn_row.addWidget(send_btn)

        problem_btn = QPushButton("Report a Problem")
        problem_btn.setStyleSheet("background: #1f6feb; color: white; padding: 8px 14px; border-radius: 6px;")
        problem_btn.clicked.connect(self._handle_problem)
        btn_row.addWidget(problem_btn)

        skip_btn = QPushButton("Don't Send")
        skip_btn.setStyleSheet("background: #21262d; color: #8b949e; padding: 8px 14px; border-radius: 6px;")
        skip_btn.clicked.connect(self._handle_skip)
        btn_row.addWidget(skip_btn)

        layout.addLayout(btn_row)

    def _handle_send(self) -> None:
        self.accept()
        if self.on_send_report:
            self.on_send_report(True)

    def _handle_problem(self) -> None:
        self.accept()
        if self.on_report_problem:
            self.on_report_problem()

    def _handle_skip(self) -> None:
        self.reject()
        if self.on_send_report:
            self.on_send_report(False)


class SafeModeDialog(QDialog if PYQT_AVAILABLE else object):
    """Notification displayed when startup crash-loop forces Safe Mode."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_restart_normal: Optional[Callable[[], None]] = None,
        on_open_support: Optional[Callable[[], None]] = None,
    ):
        if not PYQT_AVAILABLE:
            return
        super().__init__(parent)
        self.on_restart_normal = on_restart_normal
        self.on_open_support = on_open_support
        self.setWindowTitle("CHARLIE Safe Mode")
        self.setFixedSize(540, 320)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("🛡️ CHARLIE started in Safe Mode")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #d29922;")
        layout.addWidget(title)

        desc = QLabel(
            "Repeated startup failures were detected. To protect your system, third-party plugins "
            "and experimental background services are temporarily disabled.\n\n"
            "Core features, diagnostics, license management, and customer support remain available."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8b949e; font-size: 13px;")
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        continue_btn = QPushButton("Continue in Safe Mode")
        continue_btn.setStyleSheet("background: #238636; color: white; padding: 8px 14px; border-radius: 6px;")
        continue_btn.clicked.connect(self.accept)
        btn_row.addWidget(continue_btn)

        restart_btn = QPushButton("Restart Normally")
        restart_btn.setStyleSheet("background: #1f6feb; color: white; padding: 8px 14px; border-radius: 6px;")
        restart_btn.clicked.connect(self._handle_restart)
        btn_row.addWidget(restart_btn)

        support_btn = QPushButton("Get Help & Support")
        support_btn.setStyleSheet("background: #21262d; color: #8b949e; padding: 8px 14px; border-radius: 6px;")
        support_btn.clicked.connect(self._handle_support)
        btn_row.addWidget(support_btn)

        layout.addLayout(btn_row)

    def _handle_restart(self) -> None:
        self.accept()
        if self.on_restart_normal:
            self.on_restart_normal()

    def _handle_support(self) -> None:
        self.accept()
        if self.on_open_support:
            self.on_open_support()


class SupportCenterWidget(QFrame if PYQT_AVAILABLE else object):
    """Customer-facing Help & Support center with ticket creation, message threads, and diagnostics preview."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_create_ticket: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_run_self_diagnose: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        if not PYQT_AVAILABLE:
            return
        super().__init__(parent)
        self.on_create_ticket = on_create_ticket
        self.on_run_self_diagnose = on_run_self_diagnose
        self.setObjectName("supportCenterWidget")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QLabel("CHARLIE Customer Support & Remote Diagnostics")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #58a6ff;")
        layout.addWidget(header)

        info = QLabel("View system diagnostics, check known issues, or submit an inquiry to our support staff.")
        info.setStyleSheet("color: #8b949e; font-size: 13px;")
        layout.addWidget(info)

