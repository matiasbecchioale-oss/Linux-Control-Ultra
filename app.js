const modules = [
  {
    id: "system",
    title: "Panel general",
    group: "Sistema",
    icon: "gauge",
    settings: [
      {
        icon: "cpu",
        name: "Planificador y CPU",
        desc: "Gobernador, afinidad y prioridad base para cargas interactivas o servidor.",
        controls: [
          {
            type: "select",
            key: "cpuGovernor",
            label: "Gobernador de frecuencia",
            value: "schedutil",
            options: ["performance", "schedutil", "powersave"],
            command: (v) => `sudo cpupower frequency-set -g ${v}`,
          },
          {
            type: "range",
            key: "kernelTimer",
            label: "Kernel timer slack",
            min: 1,
            max: 50000,
            value: 5000,
            suffix: "ns",
            command: (v) => `echo ${v} | sudo tee /proc/self/timerslack_ns`,
          },
        ],
      },
      {
        icon: "memory-stick",
        name: "Memoria y cache",
        desc: "Politicas vm para equipos de escritorio, laboratorio o virtualizacion.",
        controls: [
          {
            type: "range",
            key: "swappiness",
            label: "vm.swappiness",
            min: 1,
            max: 100,
            value: 20,
            suffix: "%",
            command: (v) => `sudo sysctl -w vm.swappiness=${v}`,
          },
          {
            type: "toggle",
            key: "zram",
            label: "Activar zram persistente",
            value: true,
            command: (v) =>
              v
                ? "sudo systemctl enable --now systemd-zram-setup@zram0.service"
                : "sudo systemctl disable --now systemd-zram-setup@zram0.service",
          },
        ],
      },
    ],
  },
  {
    id: "security",
    title: "Seguridad avanzada",
    group: "Seguridad",
    icon: "shield",
    settings: [
      {
        icon: "lock-keyhole",
        name: "Hardening del kernel",
        desc: "Reduce superficie de ataque y expone menos informacion sensible.",
        controls: [
          {
            type: "toggle",
            key: "restrictDmesg",
            label: "Restringir dmesg a administradores",
            value: true,
            command: (v) => `sudo sysctl -w kernel.dmesg_restrict=${v ? 1 : 0}`,
          },
          {
            type: "toggle",
            key: "ptrace",
            label: "Bloquear ptrace entre usuarios",
            value: true,
            command: (v) => `sudo sysctl -w kernel.yama.ptrace_scope=${v ? 2 : 0}`,
          },
        ],
      },
      {
        icon: "fingerprint",
        name: "Autenticacion y auditoria",
        desc: "Registro de eventos, sudo mas estricto y sesiones auditables.",
        controls: [
          {
            type: "select",
            key: "auditLevel",
            label: "Nivel de auditoria",
            value: "alto",
            options: ["basico", "alto", "forense"],
            command: (v) => `sudo augenrules --load # perfil ${v}`,
          },
          {
            type: "toggle",
            key: "sudoTty",
            label: "Requerir TTY para sudo",
            value: false,
            command: (v) =>
              v
                ? "echo 'Defaults requiretty' | sudo tee /etc/sudoers.d/90-requiretty"
                : "sudo rm -f /etc/sudoers.d/90-requiretty",
          },
        ],
      },
    ],
  },
  {
    id: "network",
    title: "Red y firewall",
    group: "Conectividad",
    icon: "network",
    settings: [
      {
        icon: "router",
        name: "Pila TCP/IP",
        desc: "Congestion control, buffers y protecciones contra trafico malicioso.",
        controls: [
          {
            type: "select",
            key: "tcpCongestion",
            label: "TCP congestion control",
            value: "bbr",
            options: ["bbr", "cubic", "reno"],
            command: (v) => `sudo sysctl -w net.ipv4.tcp_congestion_control=${v}`,
          },
          {
            type: "toggle",
            key: "synCookies",
            label: "SYN cookies",
            value: true,
            command: (v) => `sudo sysctl -w net.ipv4.tcp_syncookies=${v ? 1 : 0}`,
          },
        ],
      },
      {
        icon: "brick-wall",
        name: "Firewall",
        desc: "Reglas base para estaciones, servidores y laboratorios.",
        controls: [
          {
            type: "segment",
            key: "firewallMode",
            label: "Politica entrante",
            value: "strict",
            options: ["open", "work", "strict"],
            command: (v) => `sudo ufw default ${v === "open" ? "allow" : "deny"} incoming`,
          },
          {
            type: "text",
            key: "allowedPorts",
            label: "Puertos permitidos",
            value: "22, 443",
            command: (v) =>
              v
                .split(",")
                .map((port) => `sudo ufw allow ${port.trim()}`)
                .filter(Boolean)
                .join("\n"),
          },
        ],
      },
    ],
  },
  {
    id: "storage",
    title: "Almacenamiento",
    group: "Discos",
    icon: "hard-drive",
    settings: [
      {
        icon: "database-zap",
        name: "I/O y SSD",
        desc: "Planificador de disco, TRIM y escritura segura.",
        controls: [
          {
            type: "select",
            key: "ioScheduler",
            label: "Scheduler I/O",
            value: "mq-deadline",
            options: ["none", "mq-deadline", "bfq"],
            command: (v) => `echo ${v} | sudo tee /sys/block/nvme0n1/queue/scheduler`,
          },
          {
            type: "toggle",
            key: "trim",
            label: "TRIM semanal",
            value: true,
            command: (v) => `sudo systemctl ${v ? "enable --now" : "disable --now"} fstrim.timer`,
          },
        ],
      },
      {
        icon: "archive-restore",
        name: "Snapshots y rollback",
        desc: "Puntos de restauracion antes de operaciones delicadas.",
        controls: [
          {
            type: "segment",
            key: "snapshotPolicy",
            label: "Retencion",
            value: "daily",
            options: ["manual", "daily", "hourly"],
            command: (v) => `sudo snapper set-config TIMELINE_CREATE=${v !== "manual"}`,
          },
          {
            type: "number",
            key: "snapshotLimit",
            label: "Maximo de snapshots",
            value: 12,
            min: 1,
            max: 80,
            command: (v) => `sudo snapper set-config NUMBER_LIMIT=${v}`,
          },
        ],
      },
    ],
  },
  {
    id: "services",
    title: "Servicios y arranque",
    group: "Arranque",
    icon: "power",
    settings: [
      {
        icon: "rocket",
        name: "Boot y systemd",
        desc: "Reduce latencia de arranque y controla unidades criticas.",
        controls: [
          {
            type: "toggle",
            key: "resolved",
            label: "systemd-resolved",
            value: true,
            command: (v) => `sudo systemctl ${v ? "enable --now" : "disable --now"} systemd-resolved`,
          },
          {
            type: "toggle",
            key: "bluetooth",
            label: "Bluetooth al iniciar",
            value: false,
            command: (v) => `sudo systemctl ${v ? "enable --now" : "disable --now"} bluetooth`,
          },
        ],
      },
      {
        icon: "timer-reset",
        name: "Tareas programadas",
        desc: "Mantenimiento, limpieza y chequeos automaticos.",
        controls: [
          {
            type: "toggle",
            key: "journalVacuum",
            label: "Limpiar journal mensualmente",
            value: true,
            command: (v) =>
              v
                ? "sudo systemctl enable --now journal-vacuum.timer"
                : "sudo systemctl disable --now journal-vacuum.timer",
          },
          {
            type: "number",
            key: "journalSize",
            label: "Tamano maximo journal",
            value: 512,
            min: 64,
            max: 4096,
            command: (v) => `sudo journalctl --vacuum-size=${v}M`,
          },
        ],
      },
    ],
  },
  {
    id: "containers",
    title: "Virtualizacion",
    group: "Laboratorio",
    icon: "boxes",
    settings: [
      {
        icon: "box",
        name: "Contenedores",
        desc: "Ajustes para Podman, Docker rootless y redes aisladas.",
        controls: [
          {
            type: "toggle",
            key: "rootlessContainers",
            label: "Habilitar subuid/subgid rootless",
            value: true,
            command: (v) =>
              v
                ? "sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 $USER"
                : "# Revisar /etc/subuid y /etc/subgid antes de retirar rangos",
          },
          {
            type: "segment",
            key: "containerNet",
            label: "Modo de red",
            value: "isolated",
            options: ["host", "bridged", "isolated"],
            command: (v) => `podman network create --driver bridge lab-${v}`,
          },
        ],
      },
      {
        icon: "monitor-cog",
        name: "KVM/QEMU",
        desc: "Preparacion para maquinas virtuales con aceleracion.",
        controls: [
          {
            type: "toggle",
            key: "libvirt",
            label: "libvirtd activo",
            value: true,
            command: (v) => `sudo systemctl ${v ? "enable --now" : "disable --now"} libvirtd`,
          },
          {
            type: "toggle",
            key: "iommu",
            label: "IOMMU en GRUB",
            value: false,
            command: (v) =>
              v
                ? "sudo grubby --update-kernel=ALL --args='intel_iommu=on amd_iommu=on'"
                : "sudo grubby --update-kernel=ALL --remove-args='intel_iommu=on amd_iommu=on'",
          },
        ],
      },
    ],
  },
];

const profiles = ["Equilibrado", "Rendimiento", "Servidor seguro", "Bateria", "Laboratorio"];
const state = {
  activeModule: modules[0].id,
  profileIndex: 0,
  values: {},
  changed: new Set(),
};

const els = {
  moduleList: document.querySelector("#moduleList"),
  settingsPanel: document.querySelector("#settingsPanel"),
  searchInput: document.querySelector("#searchInput"),
  moduleTitle: document.querySelector("#moduleTitle"),
  moduleEyebrow: document.querySelector("#moduleEyebrow"),
  commandPreview: document.querySelector("#commandPreview"),
  pendingList: document.querySelector("#pendingList"),
  changeCount: document.querySelector("#changeCount"),
  planTitle: document.querySelector("#planTitle"),
  profileName: document.querySelector("#profileName"),
  toast: document.querySelector("#toast"),
};

function initValues() {
  modules.forEach((module) => {
    module.settings.forEach((setting) => {
      setting.controls.forEach((control) => {
        state.values[control.key] = control.value;
      });
    });
  });
}

function getActiveModule() {
  return modules.find((module) => module.id === state.activeModule);
}

function renderModules() {
  const query = els.searchInput.value.trim().toLowerCase();
  els.moduleList.innerHTML = "";

  modules
    .filter((module) => {
      const content = [module.title, module.group, ...module.settings.map((setting) => setting.name)]
        .join(" ")
        .toLowerCase();
      return content.includes(query);
    })
    .forEach((module) => {
      const button = document.createElement("button");
      button.className = `module-button ${module.id === state.activeModule ? "active" : ""}`;
      button.innerHTML = `
        <i data-lucide="${module.icon}"></i>
        <span>${module.title}</span>
        <span class="badge">${module.group}</span>
      `;
      button.addEventListener("click", () => {
        state.activeModule = module.id;
        render();
      });
      els.moduleList.appendChild(button);
    });
}

function renderSettings() {
  const module = getActiveModule();
  els.moduleTitle.textContent = module.title;
  els.moduleEyebrow.textContent = module.group;
  els.settingsPanel.innerHTML = "";

  module.settings.forEach((setting) => {
    const card = document.createElement("article");
    card.className = "setting-card";
    card.innerHTML = `
      <div class="setting-title">
        <i data-lucide="${setting.icon}"></i>
        <div>
          <h2>${setting.name}</h2>
          <p class="setting-copy">${setting.desc}</p>
        </div>
      </div>
    `;

    setting.controls.forEach((control) => {
      card.appendChild(createControl(control));
    });

    els.settingsPanel.appendChild(card);
  });
}

function createControl(control) {
  if (control.type === "toggle") {
    const wrapper = document.createElement("label");
    wrapper.className = "switch";
    wrapper.innerHTML = `
      <span>${control.label}</span>
      <input type="checkbox" ${state.values[control.key] ? "checked" : ""} />
    `;
    wrapper.querySelector("input").addEventListener("change", (event) => {
      updateValue(control.key, event.target.checked);
    });
    return wrapper;
  }

  if (control.type === "segment") {
    const wrapper = document.createElement("div");
    wrapper.className = "control-row";
    wrapper.innerHTML = `<label>${control.label}</label>`;
    const segmented = document.createElement("div");
    segmented.className = "segmented";
    control.options.forEach((option) => {
      const button = document.createElement("button");
      button.textContent = option;
      button.className = option === state.values[control.key] ? "active" : "";
      button.addEventListener("click", () => updateValue(control.key, option));
      segmented.appendChild(button);
    });
    wrapper.appendChild(segmented);
    return wrapper;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "control-row";
  const value = state.values[control.key];
  const suffix = control.suffix ? ` <span class="hint">${value}${control.suffix}</span>` : "";
  wrapper.innerHTML = `<label for="${control.key}">${control.label}${suffix}</label>`;

  const input = document.createElement(control.type === "select" ? "select" : "input");
  input.id = control.key;

  if (control.type === "select") {
    control.options.forEach((option) => {
      const item = document.createElement("option");
      item.value = option;
      item.textContent = option;
      item.selected = option === value;
      input.appendChild(item);
    });
  } else {
    input.type = control.type;
    input.value = value;
    if (control.min !== undefined) input.min = control.min;
    if (control.max !== undefined) input.max = control.max;
  }

  input.addEventListener("input", (event) => {
    const nextValue = control.type === "number" || control.type === "range" ? Number(event.target.value) : event.target.value;
    updateValue(control.key, nextValue);
  });
  wrapper.appendChild(input);
  return wrapper;
}

function updateValue(key, value) {
  state.values[key] = value;
  state.changed.add(key);
  render();
}

function allControls() {
  return modules.flatMap((module) =>
    module.settings.flatMap((setting) =>
      setting.controls.map((control) => ({
        ...control,
        setting: setting.name,
        module: module.title,
      })),
    ),
  );
}

function renderInspector() {
  const controls = allControls().filter((control) => state.changed.has(control.key));
  els.changeCount.textContent = String(controls.length);
  els.planTitle.textContent = controls.length ? `${controls.length} ajustes listos` : "Sin cambios";

  if (!controls.length) {
    els.commandPreview.textContent = "# Ajusta controles para generar comandos seguros.";
    els.pendingList.innerHTML = "<li>No hay cambios pendientes.</li>";
    return;
  }

  els.commandPreview.textContent = [
    "# Revisar antes de ejecutar. Algunos comandos dependen de la distribucion.",
    "sudo true",
    ...controls.map((control) => control.command(state.values[control.key])),
  ].join("\n");

  els.pendingList.innerHTML = controls
    .map((control) => `<li><strong>${control.label}</strong>: ${String(state.values[control.key])}</li>`)
    .join("");
}

function updateStatus() {
  document.querySelector("#cpuState").textContent = state.values.cpuGovernor;
  document.querySelector("#swapState").textContent = state.values.swappiness;
  document.querySelector("#securityState").textContent = state.values.auditLevel === "forense" ? "Forense" : "Alto";
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.setTimeout(() => els.toast.classList.remove("show"), 2200);
}

function render() {
  renderModules();
  renderSettings();
  renderInspector();
  updateStatus();
  if (window.lucide) {
    lucide.createIcons();
  }
}

document.querySelector("#cycleProfile").addEventListener("click", () => {
  state.profileIndex = (state.profileIndex + 1) % profiles.length;
  els.profileName.textContent = profiles[state.profileIndex];
  toast(`Perfil ${profiles[state.profileIndex]} seleccionado`);
});

document.querySelector("#copyCommands").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(els.commandPreview.textContent);
    toast("Comandos copiados");
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(els.commandPreview);
    selection.removeAllRanges();
    selection.addRange(range);
    toast("Plan seleccionado para copiar");
  }
});

document.querySelector("#exportPlan").addEventListener("click", () => {
  const blob = new Blob([els.commandPreview.textContent], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "plan-configuracion-linux.sh";
  link.click();
  URL.revokeObjectURL(url);
  toast("Plan exportado");
});

document.querySelector("#applyChanges").addEventListener("click", () => {
  toast("Modo seguro: revisa y ejecuta el plan exportado");
});

els.searchInput.addEventListener("input", renderModules);

initValues();
render();
