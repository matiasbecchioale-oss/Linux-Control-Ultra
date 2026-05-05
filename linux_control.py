#!/usr/bin/env python3
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import paramiko
import psutil
import pyqtgraph as pg
import yaml

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Linux Control Ultra"


@dataclass(frozen=True)
class Setting:
    key: str
    module: str
    category: str
    name: str
    kind: str
    default: object
    choices: tuple
    command: str
    risk: str
    requires_root: bool
    description: str


MODULES = [
    ("dashboard", "Panel general", "SP_ComputerIcon"),
    ("kernel", "Kernel y sysctl", "SP_DriveHDIcon"),
    ("cpu", "CPU y energia", "SP_MediaPlay"),
    ("memory", "Memoria y swap", "SP_DriveFDIcon"),
    ("network", "Red avanzada", "SP_DriveNetIcon"),
    ("firewall", "Firewall", "SP_MessageBoxWarning"),
    ("storage", "Discos y filesystem", "SP_DirIcon"),
    ("security", "Seguridad", "SP_DialogApplyButton"),
    ("services", "Systemd y servicios", "SP_BrowserReload"),
    ("containers", "Contenedores", "SP_FileDialogDetailedView"),
    ("virtualization", "Virtualizacion", "SP_DesktopIcon"),
    ("desktop", "Escritorio", "SP_TitleBarNormalButton"),
    ("logs", "Logs y auditoria", "SP_FileIcon"),
    ("packages", "Paquetes", "SP_DialogOpenButton"),
    ("backup", "Backups", "SP_DialogSaveButton"),
    ("lab", "Laboratorio", "SP_DialogHelpButton"),
]


BASE_SETTINGS = [
    Setting(
        "cpu.governor",
        "cpu",
        "Frecuencia",
        "Gobernador de CPU",
        "choice",
        "schedutil",
        ("performance", "schedutil", "powersave"),
        "sudo cpupower frequency-set -g {value}",
        "medio",
        True,
        "Controla el perfil de frecuencia del procesador.",
    ),
    Setting(
        "vm.swappiness",
        "memory",
        "VM",
        "vm.swappiness",
        "number",
        20,
        (),
        "sudo sysctl -w vm.swappiness={value}",
        "bajo",
        True,
        "Define cuanto prefiere el kernel usar swap.",
    ),
    Setting(
        "net.tcp_congestion_control",
        "network",
        "TCP",
        "TCP congestion control",
        "choice",
        "bbr",
        ("bbr", "cubic", "reno"),
        "sudo sysctl -w net.ipv4.tcp_congestion_control={value}",
        "medio",
        True,
        "Selecciona el algoritmo de congestion TCP.",
    ),
    Setting(
        "security.dmesg_restrict",
        "security",
        "Kernel hardening",
        "Restringir dmesg",
        "bool",
        True,
        (),
        "sudo sysctl -w kernel.dmesg_restrict={value01}",
        "bajo",
        True,
        "Evita que usuarios no privilegiados lean mensajes del kernel.",
    ),
    Setting(
        "security.ptrace_scope",
        "security",
        "Kernel hardening",
        "Bloquear ptrace entre usuarios",
        "choice",
        "2",
        ("0", "1", "2", "3"),
        "sudo sysctl -w kernel.yama.ptrace_scope={value}",
        "alto",
        True,
        "Limita depuracion entre procesos de distintos usuarios.",
    ),
    Setting(
        "storage.trim",
        "storage",
        "SSD",
        "TRIM semanal",
        "bool",
        True,
        (),
        "sudo systemctl {enable_disable_now} fstrim.timer",
        "bajo",
        True,
        "Activa mantenimiento periodico TRIM en unidades SSD.",
    ),
    Setting(
        "services.bluetooth",
        "services",
        "Arranque",
        "Bluetooth al iniciar",
        "bool",
        False,
        (),
        "sudo systemctl {enable_disable_now} bluetooth",
        "bajo",
        True,
        "Controla si Bluetooth arranca automaticamente.",
    ),
    Setting(
        "containers.rootless",
        "containers",
        "Rootless",
        "Rangos subuid/subgid para contenedores",
        "bool",
        True,
        (),
        "sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 $USER",
        "medio",
        True,
        "Prepara usuarios para contenedores sin root.",
    ),
]


GENERATORS = [
    ("kernel", "Sysctl", "kernel.tuning.{i}", "Kernel tuning parametro {i}", "number", 0, "sudo sysctl -w kernel.custom_{i}={value}"),
    ("kernel", "Scheduler", "kernel.scheduler.{i}", "Politica scheduler {i}", "choice", "auto", "echo {value} | sudo tee /proc/sys/kernel/sched_custom_{i}"),
    ("cpu", "Nucleos", "cpu.core.{i}", "Afinidad del nucleo {i}", "choice", "auto", "sudo tuna --cpus={i} --isolate={value}"),
    ("cpu", "Energia", "cpu.energy.{i}", "Parametro energia {i}", "number", 50, "sudo powertop --auto-tune # energia {i}={value}"),
    ("memory", "Cache", "memory.cache.{i}", "Presion de cache {i}", "number", 100, "sudo sysctl -w vm.vfs_cache_pressure={value}"),
    ("memory", "HugePages", "memory.hugepages.{i}", "HugePages grupo {i}", "number", 0, "sudo sysctl -w vm.nr_hugepages={value}"),
    ("network", "TCP", "network.tcp.{i}", "Parametro TCP {i}", "number", 1, "sudo sysctl -w net.ipv4.tcp_custom_{i}={value}"),
    ("network", "Interfaces", "network.iface.{i}", "Optimizacion interfaz {i}", "choice", "balanced", "sudo ethtool -K eth0 feature{i} {value}"),
    ("firewall", "Reglas", "firewall.rule.{i}", "Regla firewall {i}", "bool", False, "sudo ufw {allow_deny} {port}"),
    ("firewall", "Zonas", "firewall.zone.{i}", "Zona de confianza {i}", "choice", "work", "sudo firewall-cmd --set-default-zone={value}"),
    ("storage", "I/O", "storage.io.{i}", "Scheduler de disco {i}", "choice", "mq-deadline", "echo {value} | sudo tee /sys/block/sda/queue/scheduler"),
    ("storage", "Mount", "storage.mount.{i}", "Opcion de montaje {i}", "bool", True, "sudo mount -o remount,{mount_option} /"),
    ("security", "Hardening", "security.hardening.{i}", "Control de hardening {i}", "bool", True, "sudo sysctl -w kernel.hardening_{i}={value01}"),
    ("security", "Usuarios", "security.users.{i}", "Politica de usuario {i}", "choice", "strict", "sudo authselect select custom/{value}"),
    ("services", "Systemd", "services.unit.{i}", "Servicio gestionado {i}", "bool", False, "sudo systemctl {enable_disable_now} servicio-{i}.service"),
    ("services", "Timers", "services.timer.{i}", "Timer de mantenimiento {i}", "bool", True, "sudo systemctl {enable_disable_now} mantenimiento-{i}.timer"),
    ("containers", "Podman", "containers.podman.{i}", "Ajuste Podman {i}", "choice", "isolated", "podman system service --time={number}"),
    ("containers", "Docker", "containers.docker.{i}", "Ajuste Docker {i}", "bool", False, "sudo systemctl {enable_disable_now} docker"),
    ("virtualization", "KVM", "virt.kvm.{i}", "Parametro KVM {i}", "bool", True, "sudo modprobe kvm # kvm parametro {i}={value01}"),
    ("virtualization", "QEMU", "virt.qemu.{i}", "Perfil QEMU {i}", "choice", "balanced", "virsh net-autostart default # {value}"),
    ("desktop", "GNOME/KDE", "desktop.ui.{i}", "Ajuste visual {i}", "choice", "system", "gsettings set org.example.setting{i} mode '{value}'"),
    ("desktop", "Entrada", "desktop.input.{i}", "Entrada dispositivo {i}", "number", 10, "xinput set-prop {i} 'libinput Accel Speed' {value}"),
    ("logs", "Journal", "logs.journal.{i}", "Limite journal {i}", "number", 512, "sudo journalctl --vacuum-size={value}M"),
    ("logs", "Audit", "logs.audit.{i}", "Regla auditd {i}", "bool", True, "sudo auditctl -w /etc -p wa -k config-{i}"),
    ("packages", "Repos", "packages.repo.{i}", "Repositorio controlado {i}", "bool", False, "sudo dnf config-manager --set-{enable_disable} repo-{i}"),
    ("packages", "Limpieza", "packages.clean.{i}", "Politica limpieza {i}", "choice", "safe", "sudo package-cleanup --{value}"),
    ("backup", "Snapshots", "backup.snapshot.{i}", "Snapshot automatico {i}", "bool", True, "sudo snapper set-config TIMELINE_CREATE={value_bool}"),
    ("backup", "Retencion", "backup.retention.{i}", "Retencion backup {i}", "number", 14, "sudo snapper set-config NUMBER_LIMIT={value}"),
    ("lab", "Experimentos", "lab.exp.{i}", "Experimento controlado {i}", "choice", "off", "echo lab_exp_{i}={value}"),
    ("lab", "Benchmarks", "lab.bench.{i}", "Benchmark perfil {i}", "bool", False, "echo benchmark_{i}={value_bool}"),
]


CHOICES = {
    "choice": ("off", "safe", "balanced", "performance", "strict"),
}


class LinuxControl(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = self.build_settings()
        self.values = {item.key: item.default for item in self.settings}
        self.pending = {}
        self.active_module = "dashboard"
        self.telemetry = {"cpu": [], "ram": [], "net": [], "temp": []}
        self.last_net = psutil.net_io_counters()
        self.security_issues = []
        self.ssh_connected = False
        self.ssh_client = None

        self.setWindowTitle(APP_NAME)
        self.resize(1440, 860)
        self.setMinimumSize(980, 640)

        self.build_ui()
        self.apply_theme()
        self.populate_modules()
        self.refresh()

        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self.update_telemetry)
        self.telemetry_timer.start(1000)

    def build_settings(self):
        settings = list(BASE_SETTINGS)
        for module, category, key, name, kind, default, command in GENERATORS:
            for i in range(1, 81):
                choices = CHOICES["choice"] if kind == "choice" else ()
                value = default
                if kind == "number":
                    value = int(default) + (i % 9)
                settings.append(
                    Setting(
                        key.format(i=i),
                        module,
                        category,
                        name.format(i=i),
                        kind,
                        value,
                        choices,
                        command.replace("{i}", str(i)),
                        "medio" if i % 5 else "alto",
                        True,
                        "Opcion avanzada generada para perfiles de administracion masivos.",
                    )
                )
        return settings

    def icon(self, name):
        enum = getattr(QStyle.StandardPixmap, name)
        return self.style().standardIcon(enum)

    def build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left = QFrame()
        left.setObjectName("sidebar")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        title = QLabel(APP_NAME)
        title.setObjectName("brand")
        subtitle = QLabel("Configuracion super avanzada del sistema")
        subtitle.setObjectName("muted")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar entre miles de opciones...")
        self.search.textChanged.connect(self.refresh_table)

        self.module_list = QListWidget()
        self.module_list.currentItemChanged.connect(self.change_module)

        left_layout.addWidget(title)
        left_layout.addWidget(subtitle)
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.module_list, 1)

        self.simulation = QCheckBox("Modo simulacion")
        self.simulation.setChecked(True)
        left_layout.addWidget(self.simulation)

        self.remote_mode = QCheckBox("Ejecutar por SSH")
        self.remote_mode.setToolTip("Usa la sesion SSH configurada en la pestana Remoto para ejecutar el plan.")
        left_layout.addWidget(self.remote_mode)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(18, 16, 18, 16)
        right_layout.setSpacing(12)
        splitter.addWidget(right)
        splitter.setSizes([320, 1120])

        header = QHBoxLayout()
        self.heading = QLabel("Panel general")
        self.heading.setObjectName("heading")
        header.addWidget(self.heading, 1)

        self.profile = QComboBox()
        self.profile.addItems(["Equilibrado", "Rendimiento", "Servidor seguro", "Bateria", "Laboratorio", "Forense"])
        self.profile.currentTextChanged.connect(self.apply_profile)
        header.addWidget(self.profile)

        right_layout.addLayout(header)

        metrics = QGridLayout()
        self.metric_total = self.metric_card("Opciones", "0")
        self.metric_pending = self.metric_card("Pendientes", "0")
        self.metric_root = self.metric_card("Requieren root", "0")
        self.metric_risk = self.metric_card("Riesgo alto", "0")
        metrics.addWidget(self.metric_total, 0, 0)
        metrics.addWidget(self.metric_pending, 0, 1)
        metrics.addWidget(self.metric_root, 0, 2)
        metrics.addWidget(self.metric_risk, 0, 3)
        right_layout.addLayout(metrics)

        tabs = QTabWidget()
        right_layout.addWidget(tabs, 1)
        self.tabs = tabs

        tabs.addTab(self.build_telemetry_tab(), self.icon("SP_ComputerIcon"), "Telemetria")
        tabs.addTab(self.build_security_tab(), self.icon("SP_DialogApplyButton"), "Score seguridad")
        tabs.addTab(self.build_recipes_tab(), self.icon("SP_DialogOpenButton"), "Recetas")
        tabs.addTab(self.build_hardware_tab(), self.icon("SP_DriveHDIcon"), "Hardware")
        tabs.addTab(self.build_ssh_tab(), self.icon("SP_DriveNetIcon"), "SSH remoto")

        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Modulo", "Categoria", "Ajuste", "Valor", "Riesgo", "Root"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemDoubleClicked.connect(self.edit_selected)
        table_layout.addWidget(self.table)

        table_actions = QHBoxLayout()
        self.edit_btn = QPushButton("Editar valor")
        self.edit_btn.setIcon(self.icon("SP_FileDialogContentsView"))
        self.edit_btn.clicked.connect(self.edit_selected)
        self.reset_btn = QPushButton("Reiniciar ajuste")
        self.reset_btn.setIcon(self.icon("SP_BrowserStop"))
        self.reset_btn.clicked.connect(self.reset_selected)
        table_actions.addWidget(self.edit_btn)
        table_actions.addWidget(self.reset_btn)
        table_actions.addStretch(1)
        table_layout.addLayout(table_actions)

        tabs.addTab(table_page, self.icon("SP_FileDialogListView"), "Opciones")

        plan_page = QWidget()
        plan_layout = QVBoxLayout(plan_page)
        plan_layout.setContentsMargins(0, 0, 0, 0)
        self.plan = QPlainTextEdit()
        self.plan.setReadOnly(True)
        mono = QFont("monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.plan.setFont(mono)
        plan_layout.addWidget(self.plan, 1)

        plan_actions = QHBoxLayout()
        actions = [
            ("Copiar", "SP_DialogSaveButton", self.copy_plan),
            ("Exportar .sh", "SP_DialogSaveButton", self.export_plan),
            ("Ejecutar", "SP_DialogApplyButton", self.execute_plan),
            ("Limpiar cola", "SP_DialogDiscardButton", self.clear_pending),
        ]
        for label, icon_name, handler in actions:
            button = QPushButton(label)
            button.setIcon(self.icon(icon_name))
            button.clicked.connect(handler)
            plan_actions.addWidget(button)
        plan_actions.addStretch(1)
        plan_layout.addLayout(plan_actions)

        tabs.addTab(plan_page, self.icon("SP_ComputerIcon"), "Plan de ejecucion")

        report_page = QWidget()
        report_layout = QVBoxLayout(report_page)
        report_layout.setContentsMargins(0, 0, 0, 0)
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        report_layout.addWidget(self.report)
        tabs.addTab(report_page, self.icon("SP_FileIcon"), "Informe")

        self.status = self.statusBar()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(180)
        self.status.addPermanentWidget(self.progress)

        about = QAction("Acerca de", self)
        about.triggered.connect(self.show_about)
        self.menuBar().addAction(about)

    def build_telemetry_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        grid = QGridLayout()
        self.cpu_live = self.metric_card("CPU actual", "0%")
        self.ram_live = self.metric_card("RAM usada", "0%")
        self.net_live = self.metric_card("Red", "0 KB/s")
        self.temp_live = self.metric_card("Temperatura", "N/D")
        grid.addWidget(self.cpu_live, 0, 0)
        grid.addWidget(self.ram_live, 0, 1)
        grid.addWidget(self.net_live, 0, 2)
        grid.addWidget(self.temp_live, 0, 3)
        layout.addLayout(grid)

        plot_grid = QGridLayout()
        self.cpu_plot, self.cpu_curve = self.make_plot("CPU %", "#40c4a7")
        self.ram_plot, self.ram_curve = self.make_plot("RAM %", "#67aaf9")
        self.net_plot, self.net_curve = self.make_plot("Red KB/s", "#f2b84b")
        self.temp_plot, self.temp_curve = self.make_plot("Temperatura C", "#ff6b6b")
        plot_grid.addWidget(self.cpu_plot, 0, 0)
        plot_grid.addWidget(self.ram_plot, 0, 1)
        plot_grid.addWidget(self.net_plot, 1, 0)
        plot_grid.addWidget(self.temp_plot, 1, 1)
        layout.addLayout(plot_grid, 1)

        return page

    def make_plot(self, title, color):
        plot = pg.PlotWidget()
        plot.setBackground("#101214")
        plot.setTitle(title, color="#eef2f5", size="11pt")
        plot.showGrid(x=True, y=True, alpha=0.22)
        plot.setYRange(0, 100)
        curve = plot.plot([], [], pen=pg.mkPen(color, width=2))
        return plot, curve

    def build_security_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        self.security_score = QProgressBar()
        self.security_score.setRange(0, 100)
        self.security_score.setFormat("Score de seguridad: %p%")
        top.addWidget(self.security_score, 1)

        optimize = QPushButton("Optimizar Seguridad")
        optimize.setIcon(self.icon("SP_DialogApplyButton"))
        optimize.clicked.connect(self.optimize_security)
        top.addWidget(optimize)

        lynis = QPushButton("Auditar con Lynis")
        lynis.setIcon(self.icon("SP_FileDialogDetailedView"))
        lynis.clicked.connect(self.run_lynis_audit)
        top.addWidget(lynis)
        layout.addLayout(top)

        self.security_table = QTableWidget(0, 4)
        self.security_table.setHorizontalHeaderLabels(["Estado", "Hallazgo", "Impacto", "Accion sugerida"])
        self.security_table.horizontalHeader().setStretchLastSection(True)
        self.security_table.setAlternatingRowColors(True)
        layout.addWidget(self.security_table, 1)

        self.lynis_output = QPlainTextEdit()
        self.lynis_output.setReadOnly(True)
        self.lynis_output.setPlaceholderText("La salida resumida de Lynis aparecera aqui si esta instalado.")
        layout.addWidget(self.lynis_output)
        return page

    def build_recipes_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        actions = QHBoxLayout()
        for label, icon_name, handler in [
            ("Exportar receta", "SP_DialogSaveButton", self.export_recipe),
            ("Importar receta", "SP_DialogOpenButton", self.import_recipe),
            ("Laptop Gamer", "SP_MediaPlay", lambda: self.load_builtin_recipe("Laptop Gamer")),
            ("Servidor Web Seguro", "SP_DialogApplyButton", lambda: self.load_builtin_recipe("Servidor Web Seguro")),
            ("Workstation Dev", "SP_ComputerIcon", lambda: self.load_builtin_recipe("Workstation de Desarrollo")),
        ]:
            button = QPushButton(label)
            button.setIcon(self.icon(icon_name))
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.recipe_preview = QPlainTextEdit()
        self.recipe_preview.setReadOnly(True)
        self.recipe_preview.setPlainText(
            "Las recetas son archivos JSON/YAML con valores de ajustes, perfil y metadatos.\n"
            "Puedes exportar tu cola actual o importar una receta descargada."
        )
        layout.addWidget(self.recipe_preview, 1)
        return page

    def build_hardware_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        actions = QHBoxLayout()
        refresh = QPushButton("Actualizar diagnostico")
        refresh.setIcon(self.icon("SP_BrowserReload"))
        refresh.clicked.connect(self.refresh_hardware)
        actions.addWidget(refresh)

        self.temp_limit = QSpinBox()
        self.temp_limit.setRange(40, 110)
        self.temp_limit.setValue(80)
        self.temp_limit.setSuffix(" C limite")
        actions.addWidget(self.temp_limit)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.hardware_report = QTextEdit()
        self.hardware_report.setReadOnly(True)
        layout.addWidget(self.hardware_report, 1)
        return page

    def build_ssh_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QGridLayout()
        self.ssh_host = QLineEdit()
        self.ssh_host.setPlaceholderText("servidor.local o 192.168.1.10")
        self.ssh_port = QSpinBox()
        self.ssh_port.setRange(1, 65535)
        self.ssh_port.setValue(22)
        self.ssh_user = QLineEdit()
        self.ssh_user.setPlaceholderText("usuario")
        self.ssh_password = QLineEdit()
        self.ssh_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ssh_password.setPlaceholderText("password opcional")
        form.addWidget(QLabel("Host"), 0, 0)
        form.addWidget(self.ssh_host, 0, 1)
        form.addWidget(QLabel("Puerto"), 0, 2)
        form.addWidget(self.ssh_port, 0, 3)
        form.addWidget(QLabel("Usuario"), 1, 0)
        form.addWidget(self.ssh_user, 1, 1)
        form.addWidget(QLabel("Password"), 1, 2)
        form.addWidget(self.ssh_password, 1, 3)
        layout.addLayout(form)

        actions = QHBoxLayout()
        connect = QPushButton("Conectar")
        connect.setIcon(self.icon("SP_DialogApplyButton"))
        connect.clicked.connect(self.connect_ssh)
        disconnect = QPushButton("Desconectar")
        disconnect.setIcon(self.icon("SP_DialogCancelButton"))
        disconnect.clicked.connect(self.disconnect_ssh)
        actions.addWidget(connect)
        actions.addWidget(disconnect)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.ssh_command = QLineEdit()
        self.ssh_command.setPlaceholderText("Comando remoto de prueba, por ejemplo: uname -a")
        layout.addWidget(self.ssh_command)

        run = QPushButton("Ejecutar comando remoto")
        run.setIcon(self.icon("SP_ArrowForward"))
        run.clicked.connect(self.run_ssh_command)
        layout.addWidget(run)

        self.ssh_output = QPlainTextEdit()
        self.ssh_output.setReadOnly(True)
        layout.addWidget(self.ssh_output, 1)
        return page

    def metric_card(self, label, value):
        box = QFrame()
        box.setObjectName("metric")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 10, 14, 10)
        name = QLabel(label)
        name.setObjectName("muted")
        number = QLabel(value)
        number.setObjectName("metricNumber")
        layout.addWidget(name)
        layout.addWidget(number)
        box.number = number
        return box

    def populate_modules(self):
        self.module_list.clear()
        for module_id, title, icon_name in MODULES:
            item = QListWidgetItem(self.icon(icon_name), title)
            item.setData(Qt.ItemDataRole.UserRole, module_id)
            self.module_list.addItem(item)
        self.module_list.setCurrentRow(0)

    def change_module(self, item):
        if item:
            self.active_module = item.data(Qt.ItemDataRole.UserRole)
            self.heading.setText(item.text())
            self.refresh_table()

    def filtered_settings(self):
        query = self.search.text().strip().lower()
        items = self.settings
        if self.active_module != "dashboard":
            items = [item for item in items if item.module == self.active_module]
        if query:
            items = [
                item
                for item in items
                if query in " ".join([item.module, item.category, item.name, item.description, item.key]).lower()
            ]
        return items

    def refresh(self):
        self.refresh_table()
        self.refresh_plan()
        self.refresh_report()
        self.refresh_security()
        self.refresh_hardware()

    def refresh_table(self):
        items = self.filtered_settings()
        self.table.setRowCount(len(items))
        for row, setting in enumerate(items):
            values = [
                self.module_title(setting.module),
                setting.category,
                setting.name,
                str(self.values[setting.key]),
                setting.risk,
                "si" if setting.requires_root else "no",
            ]
            for col, text in enumerate(values):
                cell = QTableWidgetItem(text)
                cell.setData(Qt.ItemDataRole.UserRole, setting.key)
                if setting.key in self.pending:
                    cell.setBackground(Qt.GlobalColor.darkGreen)
                elif setting.risk == "alto":
                    cell.setBackground(Qt.GlobalColor.darkYellow)
                self.table.setItem(row, col, cell)
        self.table.resizeColumnsToContents()
        self.metric_total.number.setText(str(len(self.settings)))
        self.metric_pending.number.setText(str(len(self.pending)))
        self.metric_root.number.setText(str(sum(1 for item in self.settings if item.requires_root)))
        self.metric_risk.number.setText(str(sum(1 for item in self.settings if item.risk == "alto")))
        self.progress.setValue(int((len(self.pending) / max(1, len(self.settings))) * 100))
        self.status.showMessage(f"{len(items)} opciones visibles de {len(self.settings)} totales")

    def update_telemetry(self):
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        current_net = psutil.net_io_counters()
        net_kb = ((current_net.bytes_sent + current_net.bytes_recv) - (self.last_net.bytes_sent + self.last_net.bytes_recv)) / 1024
        self.last_net = current_net
        temp = self.current_temperature()

        samples = {"cpu": cpu, "ram": ram, "net": min(net_kb, 100), "temp": temp if temp is not None else 0}
        for key, value in samples.items():
            self.telemetry[key].append(float(value))
            self.telemetry[key] = self.telemetry[key][-90:]

        self.cpu_live.number.setText(f"{cpu:.0f}%")
        self.ram_live.number.setText(f"{ram:.0f}%")
        self.net_live.number.setText(f"{net_kb:.0f} KB/s")
        self.temp_live.number.setText("N/D" if temp is None else f"{temp:.0f} C")

        x = list(range(len(self.telemetry["cpu"])))
        self.cpu_curve.setData(x, self.telemetry["cpu"])
        self.ram_curve.setData(x, self.telemetry["ram"])
        self.net_curve.setData(x, self.telemetry["net"])
        self.temp_curve.setData(x, self.telemetry["temp"])

    def current_temperature(self):
        try:
            temps = psutil.sensors_temperatures()
        except Exception:
            return None
        values = []
        for entries in temps.values():
            values.extend([entry.current for entry in entries if entry.current is not None])
        return max(values) if values else None

    def refresh_security(self):
        issues = self.collect_security_issues()
        self.security_issues = issues
        score = max(0, 100 - sum(issue["penalty"] for issue in issues))
        self.security_score.setValue(score)
        self.security_table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            values = [issue["status"], issue["title"], issue["impact"], issue["action"]]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if issue["penalty"] >= 12:
                    item.setBackground(Qt.GlobalColor.darkYellow)
                self.security_table.setItem(row, col, item)
        self.security_table.resizeColumnsToContents()

    def collect_security_issues(self):
        issues = []
        checks = [
            ("security.dmesg_restrict", True, 8, "dmesg no restringido", "Activa kernel.dmesg_restrict"),
            ("security.ptrace_scope", "2", 12, "ptrace permisivo", "Eleva kernel.yama.ptrace_scope"),
            ("storage.trim", True, 4, "TRIM desactivado", "Activa fstrim.timer"),
            ("services.bluetooth", False, 6, "Bluetooth inicia automaticamente", "Desactiva bluetooth si no se usa"),
        ]
        for key, expected, penalty, title, action in checks:
            if self.values.get(key) != expected:
                issues.append({"status": "Debil", "title": title, "impact": f"-{penalty}", "action": action, "penalty": penalty})

        for conn in self.list_listening_ports()[:20]:
            if conn["port"] not in {22, 80, 443, 631}:
                issues.append(
                    {
                        "status": "Revisar",
                        "title": f"Puerto escuchando: {conn['port']}/{conn['proto']}",
                        "impact": "-3",
                        "action": f"Validar proceso {conn['process']} o cerrar puerto",
                        "penalty": 3,
                    }
                )
        if not issues:
            issues.append({"status": "Excelente", "title": "No se detectaron hallazgos criticos", "impact": "0", "action": "Mantener monitoreo", "penalty": 0})
        return issues

    def list_listening_ports(self):
        ports = []
        try:
            connections = psutil.net_connections(kind="inet")
        except Exception:
            return ports
        for conn in connections:
            if conn.status != psutil.CONN_LISTEN or not conn.laddr:
                continue
            process = "desconocido"
            if conn.pid:
                try:
                    process = psutil.Process(conn.pid).name()
                except Exception:
                    pass
            ports.append({"port": conn.laddr.port, "proto": "tcp", "process": process})
        return sorted(ports, key=lambda item: item["port"])

    def optimize_security(self):
        secure_values = {
            "security.dmesg_restrict": True,
            "security.ptrace_scope": "2",
            "storage.trim": True,
            "services.bluetooth": False,
        }
        for key, value in secure_values.items():
            if key in self.values and self.values[key] != value:
                self.values[key] = value
                self.pending[key] = value
        self.refresh()
        QMessageBox.information(self, APP_NAME, "Se agregaron a la cola los cambios recomendados para endurecer el sistema.")

    def run_lynis_audit(self):
        if not self.command_exists("lynis"):
            self.lynis_output.setPlainText("Lynis no esta instalado. Instala el paquete 'lynis' para auditorias profundas.")
            return
        result = subprocess.run(["lynis", "audit", "system", "--quick"], text=True, capture_output=True, timeout=120)
        output = result.stdout or result.stderr
        highlights = [line for line in output.splitlines() if "Warning" in line or "Suggestion" in line or "Hardening index" in line]
        self.lynis_output.setPlainText("\n".join(highlights[-120:]) or output[-4000:])

    def command_exists(self, name):
        return subprocess.run(["which", name], capture_output=True).returncode == 0

    def refresh_hardware(self):
        if not hasattr(self, "hardware_report"):
            return
        sections = ["<h2>Diagnostico de Hardware</h2>"]
        sections.append(self.battery_report())
        sections.append(self.temperature_report())
        sections.append(self.smart_report())
        self.hardware_report.setHtml("".join(sections))

    def battery_report(self):
        batteries = sorted(Path("/sys/class/power_supply").glob("BAT*"))
        if not batteries:
            return "<h3>Bateria</h3><p>No se detecto bateria en /sys/class/power_supply.</p>"
        rows = ["<h3>Bateria</h3><ul>"]
        for battery in batteries:
            capacity = self.read_sys_value(battery / "capacity")
            status = self.read_sys_value(battery / "status")
            full = self.read_int_sys_value(battery / "energy_full") or self.read_int_sys_value(battery / "charge_full")
            design = self.read_int_sys_value(battery / "energy_full_design") or self.read_int_sys_value(battery / "charge_full_design")
            health = f"{(full / design) * 100:.1f}%" if full and design else "N/D"
            rows.append(f"<li><b>{battery.name}</b>: carga {capacity or 'N/D'}%, estado {status or 'N/D'}, salud {health}</li>")
        rows.append("</ul>")
        return "".join(rows)

    def temperature_report(self):
        temp = self.current_temperature()
        limit = self.temp_limit.value() if hasattr(self, "temp_limit") else 80
        if temp is None:
            return "<h3>Temperaturas</h3><p>No hay sensores disponibles via psutil.</p>"
        status = "ALERTA" if temp >= limit else "OK"
        return f"<h3>Temperaturas</h3><p><b>{status}</b>: maxima detectada {temp:.1f} C, limite {limit} C.</p>"

    def smart_report(self):
        disks = [path.name for path in Path("/dev").glob("sd?")] + [path.name for path in Path("/dev").glob("nvme?n?")]
        if not disks:
            return "<h3>S.M.A.R.T.</h3><p>No se detectaron discos clasicos sdX/nvmeXnX.</p>"
        if not self.command_exists("smartctl"):
            return "<h3>S.M.A.R.T.</h3><p>smartctl no esta instalado. Instala smartmontools para ver salud de discos.</p>"
        rows = ["<h3>S.M.A.R.T.</h3><ul>"]
        for disk in disks[:8]:
            result = subprocess.run(["smartctl", "-H", f"/dev/{disk}"], text=True, capture_output=True, timeout=12)
            text = result.stdout + result.stderr
            status = "desconocido"
            for line in text.splitlines():
                if "SMART overall-health" in line or "SMART Health Status" in line:
                    status = line.split(":", 1)[-1].strip()
            rows.append(f"<li><b>/dev/{disk}</b>: {status}</li>")
        rows.append("</ul>")
        return "".join(rows)

    def read_sys_value(self, path):
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return None

    def read_int_sys_value(self, path):
        value = self.read_sys_value(path)
        try:
            return int(value) if value else None
        except ValueError:
            return None

    def refresh_plan(self):
        lines = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f"# Generado por {APP_NAME}: {datetime.now().isoformat(timespec='seconds')}",
            "# Revisar antes de ejecutar. Algunas opciones dependen de la distro y del hardware.",
            "",
        ]
        if not self.pending:
            lines.append("# No hay cambios pendientes.")
        else:
            for key in sorted(self.pending):
                setting = self.setting_by_key(key)
                value = self.values[key]
                lines.append(f"# {self.module_title(setting.module)} / {setting.category} / {setting.name}")
                lines.append(self.render_command(setting, value))
                lines.append("")
        self.plan.setPlainText("\n".join(lines))

    def refresh_report(self):
        modules = {}
        for item in self.settings:
            modules.setdefault(item.module, 0)
            modules[item.module] += 1
        html = [f"<h2>{APP_NAME}</h2>"]
        html.append("<p>Centro nativo para preparar, auditar y aplicar configuracion avanzada en Linux.</p>")
        html.append("<ul>")
        html.append(f"<li><b>Opciones totales:</b> {len(self.settings)}</li>")
        html.append(f"<li><b>Cambios pendientes:</b> {len(self.pending)}</li>")
        html.append(f"<li><b>Modo simulacion:</b> {'activo' if self.simulation.isChecked() else 'desactivado'}</li>")
        html.append("</ul><h3>Modulos</h3><ul>")
        for module_id, title, _ in MODULES:
            if module_id != "dashboard":
                html.append(f"<li><b>{title}</b>: {modules.get(module_id, 0)} opciones</li>")
        html.append("</ul>")
        self.report.setHtml("".join(html))

    def selected_setting(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        key = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return self.setting_by_key(key)

    def edit_selected(self):
        setting = self.selected_setting()
        if not setting:
            return
        current = self.values[setting.key]
        ok = False
        value = current
        if setting.kind == "bool":
            value, ok = QInputDialog.getItem(
                self,
                "Editar ajuste",
                setting.name,
                ["true", "false"],
                0 if current else 1,
                False,
            )
            value = value == "true"
        elif setting.kind == "choice":
            choices = list(setting.choices or CHOICES["choice"])
            index = choices.index(current) if current in choices else 0
            value, ok = QInputDialog.getItem(self, "Editar ajuste", setting.name, choices, index, False)
        elif setting.kind == "number":
            value, ok = QInputDialog.getInt(self, "Editar ajuste", setting.name, int(current), 0, 999999, 1)
        else:
            value, ok = QInputDialog.getText(self, "Editar ajuste", setting.name, text=str(current))
        if ok:
            self.values[setting.key] = value
            self.pending[setting.key] = value
            self.refresh()

    def reset_selected(self):
        setting = self.selected_setting()
        if not setting:
            return
        self.values[setting.key] = setting.default
        self.pending.pop(setting.key, None)
        self.refresh()

    def apply_profile(self, profile):
        profile = profile.lower()
        for setting in self.settings:
            if "rendimiento" in profile and setting.kind == "choice":
                if "performance" in setting.choices:
                    self.values[setting.key] = "performance"
                    self.pending[setting.key] = self.values[setting.key]
            elif "seguro" in profile or "forense" in profile:
                if setting.module in {"security", "firewall", "logs"}:
                    if setting.kind == "bool":
                        self.values[setting.key] = True
                    elif setting.kind == "choice":
                        self.values[setting.key] = "strict" if "strict" in setting.choices else setting.default
                    self.pending[setting.key] = self.values[setting.key]
            elif "bateria" in profile and setting.module in {"cpu", "desktop", "services"}:
                if setting.kind == "bool":
                    self.values[setting.key] = False
                elif setting.kind == "choice":
                    self.values[setting.key] = "safe" if "safe" in setting.choices else setting.default
                self.pending[setting.key] = self.values[setting.key]
        self.refresh()

    def render_command(self, setting, value):
        text = setting.command
        value_text = shlex.quote(str(value))
        replacements = {
            "{value}": value_text,
            "{value01}": "1" if bool(value) else "0",
            "{value_bool}": "true" if bool(value) else "false",
            "{enable_disable_now}": "enable --now" if bool(value) else "disable --now",
            "{enable_disable}": "enabled" if bool(value) else "disabled",
            "{allow_deny}": "allow" if bool(value) else "deny",
            "{mount_option}": "noatime" if bool(value) else "relatime",
            "{port}": str(2200 + (abs(hash(setting.key)) % 2000)),
            "{number}": str(value if isinstance(value, int) else 30),
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def copy_plan(self):
        QApplication.clipboard().setText(self.plan.toPlainText())
        self.status.showMessage("Plan copiado al portapapeles", 3000)

    def export_plan(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar plan", "plan-linux-control.sh", "Shell (*.sh)")
        if not path:
            return
        Path(path).write_text(self.plan.toPlainText(), encoding="utf-8")
        os.chmod(path, 0o755)
        self.status.showMessage(f"Plan exportado: {path}", 5000)

    def export_recipe(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar receta",
            "receta-linux-control.json",
            "Recetas (*.json *.yaml *.yml)",
        )
        if not path:
            return
        payload = {
            "name": self.profile.currentText(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "app": APP_NAME,
            "values": {key: self.values[key] for key in sorted(self.pending or self.values)},
            "pending_only": bool(self.pending),
        }
        text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False) if path.endswith((".yaml", ".yml")) else json.dumps(payload, indent=2)
        Path(path).write_text(text, encoding="utf-8")
        self.recipe_preview.setPlainText(text)
        self.status.showMessage(f"Receta exportada: {path}", 5000)

    def import_recipe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar receta", "", "Recetas (*.json *.yaml *.yml)")
        if not path:
            return
        text = Path(path).read_text(encoding="utf-8")
        payload = yaml.safe_load(text) if path.endswith((".yaml", ".yml")) else json.loads(text)
        self.apply_recipe(payload)
        self.recipe_preview.setPlainText(text)

    def load_builtin_recipe(self, name):
        recipes = {
            "Laptop Gamer": {
                "name": "Laptop Gamer",
                "values": {
                    "cpu.governor": "performance",
                    "vm.swappiness": 10,
                    "net.tcp_congestion_control": "bbr",
                    "storage.trim": True,
                    "services.bluetooth": True,
                },
            },
            "Servidor Web Seguro": {
                "name": "Servidor Web Seguro",
                "values": {
                    "security.dmesg_restrict": True,
                    "security.ptrace_scope": "2",
                    "services.bluetooth": False,
                    "storage.trim": True,
                    "net.tcp_congestion_control": "bbr",
                },
            },
            "Workstation de Desarrollo": {
                "name": "Workstation de Desarrollo",
                "values": {
                    "cpu.governor": "schedutil",
                    "vm.swappiness": 20,
                    "containers.rootless": True,
                    "storage.trim": True,
                    "services.bluetooth": False,
                },
            },
        }
        payload = recipes[name]
        self.apply_recipe(payload)
        self.recipe_preview.setPlainText(json.dumps(payload, indent=2))

    def apply_recipe(self, payload):
        values = payload.get("values", {}) if isinstance(payload, dict) else {}
        applied = 0
        for key, value in values.items():
            if key in self.values:
                self.values[key] = value
                self.pending[key] = value
                applied += 1
        self.refresh()
        QMessageBox.information(self, APP_NAME, f"Receta cargada. {applied} ajustes agregados a la cola.")

    def execute_plan(self):
        if not self.pending:
            QMessageBox.information(self, APP_NAME, "No hay cambios pendientes.")
            return
        if self.simulation.isChecked():
            QMessageBox.information(self, APP_NAME, "Modo simulacion activo: exporta o copia el plan para revisarlo.")
            return
        phrase, ok = QInputDialog.getText(self, "Confirmacion requerida", "Escribe APLICAR para ejecutar comandos reales:")
        if not ok or phrase != "APLICAR":
            return
        commands = self.plan_commands()
        failures = []
        if self.remote_mode.isChecked():
            if not self.ssh_connected:
                QMessageBox.warning(self, APP_NAME, "Activa y conecta una sesion SSH antes de ejecutar remotamente.")
                return
            failures = self.execute_commands_ssh(commands)
        else:
            failures = self.execute_commands_local(commands)
        if failures:
            QMessageBox.warning(self, APP_NAME, "\n\n".join(failures[:3]))
        else:
            self.pending.clear()
            self.refresh()
            QMessageBox.information(self, APP_NAME, "Comandos ejecutados correctamente.")

    def plan_commands(self):
        return [
            line
            for line in self.plan.toPlainText().splitlines()
            if line and not line.startswith("#") and line not in {"set -euo pipefail", "#!/usr/bin/env bash"}
        ]

    def execute_commands_local(self, commands):
        failures = []
        for command in commands:
            result = subprocess.run(command, shell=True, text=True, capture_output=True)
            if result.returncode:
                failures.append(f"$ {command}\n{result.stderr or result.stdout}")
                break
        return failures

    def execute_commands_ssh(self, commands):
        failures = []
        for command in commands:
            stdin, stdout, stderr = self.ssh_client.exec_command(command, get_pty=True)
            code = stdout.channel.recv_exit_status()
            output = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
            if code:
                failures.append(f"$ {command}\n{output}")
                break
        return failures

    def connect_ssh(self):
        host = self.ssh_host.text().strip()
        user = self.ssh_user.text().strip()
        if not host or not user:
            QMessageBox.warning(self, APP_NAME, "Completa host y usuario.")
            return
        self.disconnect_ssh()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=host,
                port=self.ssh_port.value(),
                username=user,
                password=self.ssh_password.text() or None,
                timeout=10,
            )
        except Exception as exc:
            self.ssh_output.setPlainText(f"No se pudo conectar:\n{exc}")
            return
        self.ssh_client = client
        self.ssh_connected = True
        self.ssh_output.setPlainText(f"Conectado a {user}@{host}:{self.ssh_port.value()}")

    def disconnect_ssh(self):
        if self.ssh_client:
            self.ssh_client.close()
        self.ssh_client = None
        self.ssh_connected = False

    def run_ssh_command(self):
        if not self.ssh_connected:
            QMessageBox.warning(self, APP_NAME, "Primero conecta una sesion SSH.")
            return
        command = self.ssh_command.text().strip()
        if not command:
            return
        stdin, stdout, stderr = self.ssh_client.exec_command(command, get_pty=True)
        code = stdout.channel.recv_exit_status()
        output = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
        self.ssh_output.setPlainText(f"$ {command}\nexit={code}\n\n{output}")

    def clear_pending(self):
        self.pending.clear()
        self.refresh()

    def setting_by_key(self, key):
        return next(item for item in self.settings if item.key == key)

    def module_title(self, module_id):
        return next((title for key, title, _ in MODULES if key == module_id), module_id)

    def show_about(self):
        QMessageBox.information(
            self,
            APP_NAME,
            f"{APP_NAME}\n\nOpciones cargadas: {len(self.settings)}\nInterfaz nativa PyQt6 para Linux.",
        )

    def closeEvent(self, event):
        self.disconnect_ssh()
        super().closeEvent(event)

    def apply_theme(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #101214; color: #eef2f5; font-size: 14px; }
            #sidebar { background: #171b1f; border-right: 1px solid #303942; }
            #brand { font-size: 21px; font-weight: 800; }
            #heading { font-size: 28px; font-weight: 800; }
            #muted { color: #98a5af; }
            #metric { background: #171b1f; border: 1px solid #303942; border-radius: 8px; }
            #metricNumber { font-size: 24px; font-weight: 800; color: #40c4a7; }
            QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QTableWidget, QListWidget {
                background: #171b1f; color: #eef2f5; border: 1px solid #303942; border-radius: 8px;
                selection-background-color: #2f7568;
            }
            QLineEdit, QComboBox { padding: 8px; min-height: 22px; }
            QListWidget::item { padding: 10px; border-radius: 7px; }
            QListWidget::item:selected { background: #263139; color: #ffffff; }
            QHeaderView::section { background: #20262b; color: #eef2f5; padding: 8px; border: 0; }
            QPushButton {
                background: #20262b; border: 1px solid #303942; border-radius: 8px; padding: 9px 12px;
            }
            QPushButton:hover { background: #2a333a; }
            QCheckBox { spacing: 8px; }
            QTabWidget::pane { border: 1px solid #303942; border-radius: 8px; }
            QTabBar::tab { background: #171b1f; padding: 10px 14px; border: 1px solid #303942; }
            QTabBar::tab:selected { background: #263139; color: #40c4a7; }
            QProgressBar { border: 1px solid #303942; border-radius: 7px; text-align: center; }
            QProgressBar::chunk { background: #40c4a7; border-radius: 7px; }
            """
        )


def main():
    app = QApplication(sys.argv)
    window = LinuxControl()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
