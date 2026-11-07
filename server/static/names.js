// Человеческие русские названия программ и процессов Windows.
// Ключ — имя процесса в нижнем регистре. Неизвестные имена показываются
// в читаемом виде (без «.exe», с заглавной буквы).
const RU_NAMES = {
    // Браузеры
    "chrome.exe": "Google Chrome", "msedge.exe": "Microsoft Edge", "firefox.exe": "Firefox",
    "browser.exe": "Яндекс Браузер", "opera.exe": "Opera", "brave.exe": "Brave",
    "yandex.exe": "Яндекс", "vivaldi.exe": "Vivaldi",
    // Мессенджеры и соцсети
    "telegram.exe": "Telegram", "whatsapp.exe": "WhatsApp", "discord.exe": "Discord",
    "viber.exe": "Viber", "skype.exe": "Skype", "zoom.exe": "Zoom", "teams.exe": "Microsoft Teams",
    "slack.exe": "Slack", "vk.exe": "ВКонтакте", "max.exe": "MAX",
    // Игры и лаунчеры
    "steam.exe": "Steam", "steamwebhelper.exe": "Steam (веб-часть)", "epicgameslauncher.exe": "Epic Games",
    "minecraft.exe": "Minecraft", "javaw.exe": "Java (Minecraft и др.)", "java.exe": "Java",
    "robloxplayerbeta.exe": "Roblox", "valorant.exe": "Valorant", "csgo.exe": "CS:GO", "cs2.exe": "CS 2",
    "dota2.exe": "Dota 2", "fortniteclient-win64-shipping.exe": "Fortnite", "gta5.exe": "GTA V",
    "battle.net.exe": "Battle.net", "origin.exe": "EA Origin", "eadesktop.exe": "EA app",
    "riotclientservices.exe": "Riot Client", "leagueclient.exe": "League of Legends",
    "gamebar.exe": "Игровая панель Xbox", "xboxpcapp.exe": "Xbox",
    // Офис и работа
    "winword.exe": "Word", "excel.exe": "Excel", "powerpnt.exe": "PowerPoint", "outlook.exe": "Outlook",
    "onenote.exe": "OneNote", "acrord32.exe": "Adobe Reader", "acrobat.exe": "Adobe Acrobat",
    "notepad.exe": "Блокнот", "notepad++.exe": "Notepad++", "wordpad.exe": "WordPad",
    "calculator.exe": "Калькулятор", "calc.exe": "Калькулятор", "calculatorapp.exe": "Калькулятор",
    "mspaint.exe": "Paint", "snippingtool.exe": "Ножницы", "screenclippinghost.exe": "Ножницы",
    "obsidian.exe": "Obsidian", "notion.exe": "Notion", "sumatrapdf.exe": "SumatraPDF",
    // Разработка
    "code.exe": "VS Code", "pycharm64.exe": "PyCharm", "idea64.exe": "IntelliJ IDEA", "python.exe": "Python",
    "pythonw.exe": "Python (без окна)", "py.exe": "Python", "node.exe": "Node.js", "git.exe": "Git",
    "githubdesktop.exe": "GitHub Desktop", "windowsterminal.exe": "Терминал Windows",
    "cmd.exe": "Командная строка", "powershell.exe": "PowerShell", "pwsh.exe": "PowerShell 7",
    "conhost.exe": "Окно консоли", "wt.exe": "Терминал Windows", "docker desktop.exe": "Docker",
    "claude.exe": "Claude", "cursor.exe": "Cursor", "blender.exe": "Blender",
    // Медиа
    "spotify.exe": "Spotify", "vlc.exe": "VLC", "wmplayer.exe": "Проигрыватель Windows Media",
    "music.ui.exe": "Яндекс Музыка", "яндекс музыка.exe": "Яндекс Музыка", "itunes.exe": "iTunes",
    "obs64.exe": "OBS Studio", "obs32.exe": "OBS Studio", "capcut.exe": "CapCut", "capcutbeta.exe": "CapCut",
    "premiere pro.exe": "Premiere Pro", "afterfx.exe": "After Effects", "photoshop.exe": "Photoshop",
    "davinci resolve.exe": "DaVinci Resolve", "resolve.exe": "DaVinci Resolve", "audacity.exe": "Audacity",
    "photos.exe": "Фотографии", "microsoft.photos.exe": "Фотографии", "video.ui.exe": "Кино и ТВ",
    // Windows: оболочка
    "explorer.exe": "Проводник", "dwm.exe": "Диспетчер окон (DWM)", "taskmgr.exe": "Диспетчер задач",
    "searchhost.exe": "Поиск Windows", "searchapp.exe": "Поиск Windows", "searchindexer.exe": "Индексатор поиска",
    "searchprotocolhost.exe": "Индексатор поиска", "searchfilterhost.exe": "Индексатор поиска",
    "startmenuexperiencehost.exe": "Меню «Пуск»", "shellexperiencehost.exe": "Оболочка Windows",
    "textinputhost.exe": "Ввод текста Windows", "ctfmon.exe": "Языковая панель", "sihost.exe": "Узел оболочки",
    "runtimebroker.exe": "Брокер среды выполнения", "applicationframehost.exe": "Хост приложений Windows",
    "systemsettings.exe": "Параметры Windows", "widgets.exe": "Виджеты Windows",
    "widgetservice.exe": "Виджеты Windows", "lockapp.exe": "Экран блокировки", "logonui.exe": "Экран входа",
    "taskhostw.exe": "Узел задач Windows", "dllhost.exe": "Хост COM-объектов", "backgroundtaskhost.exe": "Фоновые задачи",
    "smartscreen.exe": "SmartScreen", "securityhealthsystray.exe": "Защита Windows (значок)",
    "securityhealthservice.exe": "Служба защиты Windows", "msmpeng.exe": "Антивирус Windows Defender",
    "nissrv.exe": "Сетевая защита Defender", "mpdefendercoreservice.exe": "Defender",
    "useroobebroker.exe": "Брокер настройки", "phoneexperiencehost.exe": "Связь с телефоном",
    "yourphone.exe": "Связь с телефоном", "gamingservices.exe": "Службы игр Windows",
    "onedrive.exe": "OneDrive", "msedgewebview2.exe": "Веб-компонент Edge (WebView2)",
    "crossdeviceservice.exe": "Связь между устройствами", "ctfmon": "Языковая панель",
    // Системные
    "system": "Система", "system idle process": "Простой системы", "registry": "Реестр",
    "smss.exe": "Диспетчер сеансов", "csrss.exe": "Подсистема Windows", "wininit.exe": "Инициализация Windows",
    "winlogon.exe": "Вход в систему", "services.exe": "Службы Windows", "lsass.exe": "Безопасность Windows",
    "svchost.exe": "Служба Windows", "fontdrvhost.exe": "Драйвер шрифтов", "memory compression": "Сжатие памяти",
    "spoolsv.exe": "Диспетчер печати", "wudfhost.exe": "Драйверы устройств", "audiodg.exe": "Звук Windows",
    "conhost": "Окно консоли", "dashost.exe": "Узел устройств", "wmiprvse.exe": "Инструментарий WMI",
    "unsecapp.exe": "Узел WMI", "searchfilterhost": "Индексатор поиска", "sppsvc.exe": "Лицензирование Windows",
    "wlanext.exe": "Wi-Fi", "mousocoreworker.exe": "Центр обновления Windows", "musnotification.exe": "Обновления Windows",
    "tiworker.exe": "Установка обновлений", "trustedinstaller.exe": "Установщик модулей Windows",
    "vmmem": "Виртуальная машина (WSL)", "vmwp.exe": "Виртуальная машина",
    // Драйверы и утилиты производителей
    "nvcontainer.exe": "NVIDIA", "nvidia share.exe": "NVIDIA Share", "nvidia overlay.exe": "NVIDIA Overlay",
    "nvdisplay.container.exe": "Драйвер NVIDIA", "nvbackend.exe": "NVIDIA GeForce Experience",
    "asusoptimization.exe": "ASUS", "armourycrate.service.exe": "ASUS Armoury Crate", "armourycrate.usersessionhelper.exe": "ASUS Armoury Crate",
    "rtkauduservice64.exe": "Realtek Audio", "ravbg64.exe": "Realtek Audio", "igfxem.exe": "Intel Graphics",
    "amdrssrcext.exe": "AMD Software", "radeonsoftware.exe": "AMD Software",
    // Прочее
    "winrar.exe": "WinRAR", "7zfm.exe": "7-Zip", "qbittorrent.exe": "qBittorrent", "utorrent.exe": "µTorrent",
    "anydesk.exe": "AnyDesk", "teamviewer.exe": "TeamViewer", "rustdesk.exe": "RustDesk",
    "ticktick.exe": "TickTick", "bluestacks.exe": "BlueStacks", "vmware.exe": "VMware", "virtualbox.exe": "VirtualBox",
    "vlcmediaplayer.exe": "VLC", "everything.exe": "Everything", "sharex.exe": "ShareX", "lightshot.exe": "Lightshot",
    "ccleaner64.exe": "CCleaner", "teamspeak3.exe": "TeamSpeak", "tailscale-ipn.exe": "Tailscale", "tailscaled.exe": "Tailscale",
};

function ruName(exe) {
    const key = String(exe || "").toLowerCase();
    if (RU_NAMES[key]) return RU_NAMES[key];
    // Неизвестная программа: «my_cool-app.exe» -> «My cool app»
    const base = key.replace(/\.exe$/, "").replace(/[_\-.]+/g, " ").trim();
    return base ? base.charAt(0).toUpperCase() + base.slice(1) : String(exe);
}
