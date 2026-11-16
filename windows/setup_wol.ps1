# VoxPC: настройка Windows для Wake-on-LAN и доступа с телефона (запускать от администратора)
$ErrorActionPreference = 'Continue'
Write-Host "=== VoxPC: настройка удалённого включения ===" -ForegroundColor Cyan

$adapters = Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' }
if (-not $adapters) { Write-Host "Активные сетевые адаптеры не найдены" -ForegroundColor Yellow }

foreach ($a in $adapters) {
    Write-Host "`nАдаптер: $($a.Name) ($($a.InterfaceDescription)), MAC $($a.MacAddress)" -ForegroundColor White
    try {
        Set-NetAdapterPowerManagement -Name $a.Name -WakeOnMagicPacket Enabled -ErrorAction Stop
        Write-Host "  [OK] Пробуждение по Magic Packet" -ForegroundColor Green
    } catch { Write-Host "  [!] Magic Packet: $($_.Exception.Message)" -ForegroundColor Yellow }

    foreach ($kw in @('*WakeOnMagicPacket', '*WakeOnPattern')) {
        try { Set-NetAdapterAdvancedProperty -Name $a.Name -RegistryKeyword $kw -RegistryValue 1 -ErrorAction Stop } catch {}
    }
    # Разные драйверы (Realtek, Intel) называют параметры по-своему
    foreach ($p in (Get-NetAdapterAdvancedProperty -Name $a.Name -ErrorAction SilentlyContinue)) {
        if ($p.DisplayName -match 'Shutdown Wake|Wake on Magic|WOL & Shutdown|Wake from power off') {
            try { Set-NetAdapterAdvancedProperty -Name $a.Name -DisplayName $p.DisplayName -DisplayValue 'Enabled' -ErrorAction Stop } catch {}
        }
        if ($p.DisplayName -match 'Energy Efficient|Green Ethernet|Энергосбереж') {
            try { Set-NetAdapterAdvancedProperty -Name $a.Name -DisplayName $p.DisplayName -DisplayValue 'Disabled' -ErrorAction Stop } catch {}
        }
    }
    powercfg /deviceenablewake "$($a.InterfaceDescription)" 2>$null | Out-Null
    Write-Host "  [OK] Устройству разрешено выводить ПК из сна" -ForegroundColor Green
}

# «Быстрый запуск» мешает Wake-on-LAN после выключения
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f | Out-Null
Write-Host "`n[OK] Быстрый запуск Windows отключён" -ForegroundColor Green

# Брандмауэр: доступ только из локальной сети
Remove-NetFirewallRule -DisplayName 'VoxPC API' -ErrorAction SilentlyContinue
Remove-NetFirewallRule -DisplayName 'VoxPC Discovery' -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName 'VoxPC API' -Direction Inbound -Protocol TCP -LocalPort 47800 -Action Allow -Profile Any -RemoteAddress LocalSubnet | Out-Null
New-NetFirewallRule -DisplayName 'VoxPC Discovery' -Direction Inbound -Protocol UDP -LocalPort 47801 -Action Allow -Profile Any -RemoteAddress LocalSubnet | Out-Null
Write-Host "[OK] Порты 47800/TCP и 47801/UDP открыты для локальной сети" -ForegroundColor Green

Write-Host "`nОсталось: включите 'Wake on LAN' / 'Power On by PCI-E' в BIOS/UEFI и отключите ErP." -ForegroundColor Cyan
Read-Host "`nНажмите Enter, чтобы закрыть"
