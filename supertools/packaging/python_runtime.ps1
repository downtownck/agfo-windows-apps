# ASCII-only bootstrap to avoid legacy Windows PowerShell smart-quote issues.
function Test-AGFOPython {
    param([string]$Executable)
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        $start = New-Object System.Diagnostics.ProcessStartInfo
        $start.FileName = $Executable
        $start.Arguments = '-c "import sys,tkinter;assert sys.version_info >= (3,10);print(sys.executable)"'
        $start.UseShellExecute = $false
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        $start.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($start)
        if (-not $proc.WaitForExit(7000)) {
            try { $proc.Kill() } catch {}
            $proc.Dispose()
            return $false
        }
        $passed = ($proc.ExitCode -eq 0)
        $proc.Dispose()
        return $passed
    } catch {
        return $false
    }
}

function Find-AGFOPython {
    $candidates = New-Object System.Collections.Generic.List[string]
    $registryRoots = @(
        'HKCU:\Software\Python\PythonCore',
        'HKLM:\SOFTWARE\Python\PythonCore',
        'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore'
    )
    foreach ($root in $registryRoots) {
        if (-not (Test-Path $root)) { continue }
        foreach ($version in (Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue)) {
            $install = Join-Path $version.PSPath 'InstallPath'
            try {
                $node = Get-Item -LiteralPath $install -ErrorAction Stop
                $exePath = $node.GetValue('ExecutablePath')
                $installDir = $node.GetValue('')
                if ($exePath) { $candidates.Add([string]$exePath) }
                if ($installDir) { $candidates.Add((Join-Path ([string]$installDir) 'python.exe')) }
            } catch {}
        }
    }
    foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)},
                        (Join-Path $env:LOCALAPPDATA 'Programs\Python'))) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
        foreach ($entry in (Get-ChildItem -LiteralPath $root -Filter 'Python3*' -Directory -ErrorAction SilentlyContinue)) {
            $candidates.Add((Join-Path $entry.FullName 'python.exe'))
        }
    }
    try {
        $cmd = Get-Command 'python.exe' -ErrorAction Stop
        if ($cmd.Source) { $candidates.Add($cmd.Source) }
    } catch {}
    # Prefer newest interpreter, do not trust py.exe or PATH shims without testing.
    $distinct = @($candidates | Select-Object -Unique)
    $distinct = @($distinct | Sort-Object -Descending)
    foreach ($candidate in $distinct) {
        if (Test-AGFOPython -Executable $candidate) {
            $pyw = Join-Path (Split-Path -Parent $candidate) 'pythonw.exe'
            if (-not (Test-Path -LiteralPath $pyw)) { continue }
            return [pscustomobject]@{ Python = $candidate; PythonW = $pyw }
        }
    }
    return $null
}
