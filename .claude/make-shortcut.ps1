$desktop = [Environment]::GetFolderPath('Desktop')
$shortcut = Join-Path $desktop 'Lumare.lnk'
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($shortcut)
$sc.TargetPath = 'C:\Users\blake\OneDrive\Desktop\lumare-project\start-lumare.bat'
$sc.WorkingDirectory = 'C:\Users\blake\OneDrive\Desktop\lumare-project'
$sc.WindowStyle = 1
$sc.Description = 'Launch Lumare backend, frontend, and open the app'
$sc.IconLocation = 'C:\Windows\System32\shell32.dll,137'
$sc.Save()
Write-Host "Created: $shortcut"
