<#
    Удаляет автозапуск агента "Гостевой режим ПК" из Планировщика заданий.
    Сам агент и его файлы не трогает — только задачу автозапуска.

    Запуск:
        powershell -ExecutionPolicy Bypass -File uninstall_task.ps1
#>

$ErrorActionPreference = "Stop"
$TaskName = "GuestModeAgent"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    # Если агент сейчас запущен этой задачей — сначала останавливаем,
    # чтобы не осталось "осиротевшего" процесса
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Задача '$TaskName' удалена из Планировщика заданий."
} else {
    Write-Host "Задача '$TaskName' не найдена — удалять нечего."
}
