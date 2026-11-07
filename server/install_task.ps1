<#
    Устанавливает автозапуск сервера-панели "Гостевой режим ПК" через Планировщик
    заданий Windows: запуск при входе пользователя в систему и
    автоматический перезапуск в случае падения.

    ВАЖНО: запускайте установку автозапуска только ПОСЛЕ того, как
    протестировали агент вручную — сначала в DRY_RUN=true, потом короткий
    боевой запуск на 5 минут при вас. См. README.md, раздел "Порядок работы".

    Запуск (из папки agent/, обычный пользователь, админ-права не нужны):
        powershell -ExecutionPolicy Bypass -File install_task.ps1
#>

$ErrorActionPreference = "Stop"

$TaskName = "GuestModeServer"
$AgentDir = $PSScriptRoot
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    throw "Python не найден в PATH. Установите Python и повторите попытку."
}
$PythonExe = $PythonCmd.Source
$ScriptPath = Join-Path $AgentDir "main.py"

Write-Host "Папка сервера: $AgentDir"
Write-Host "Python:       $PythonExe"
Write-Host "Скрипт:       $ScriptPath"

if (-not (Test-Path $ScriptPath)) {
    throw "Не найден main.py по пути $ScriptPath"
}
if (-not (Test-Path (Join-Path $AgentDir ".env"))) {
    Write-Warning "Файл .env не найден в $AgentDir — сервер не запустится без настроек. Скопируйте .env.example в .env."
}

# Действие: запустить python main.py с рабочей папкой = папка агента
# (важно для относительных путей — .env и лог-файл лежат рядом со скриптом)
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`"" -WorkingDirectory $AgentDir

# Триггер: при входе текущего пользователя в систему
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Настройки: перезапуск при падении, без ограничения по времени работы
$Settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -Hidden

$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-Host "Задача '$TaskName' уже существует — удаляю старую версию перед переустановкой..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal `
    -Description "Сервер-панель «Гостевой режим ПК» (автозапуск при входе в систему)" | Out-Null

Write-Host ""
Write-Host "Готово. Задача '$TaskName' создана в Планировщике заданий."
Write-Host "Запустить прямо сейчас:  Start-ScheduledTask -TaskName $TaskName"
Write-Host "Проверить статус:        Get-ScheduledTask -TaskName $TaskName"
Write-Host "Удалить автозапуск:      .\uninstall_task.ps1"
