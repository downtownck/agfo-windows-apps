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

function Find-AGFOPythons {
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
    # Interpreters are tested (tkinter import) and ordered: versions PyInstaller supports best (3.10-3.13) first,
    # then the rest, each group newest first. The build tries them in this order until the EXE self-test passes.
    $found = @()
    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        if (-not (Test-AGFOPython -Executable $candidate)) { continue }
        $pyw = Join-Path (Split-Path -Parent $candidate) 'pythonw.exe'
        if (-not (Test-Path -LiteralPath $pyw)) { continue }
        $ver = $null
        try {
            $out = (& $candidate -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null | Select-Object -First 1)
            $ver = [version]("$out".Trim())
        } catch {}
        if (-not $ver) { continue }
        $found += [pscustomobject]@{ Python = $candidate; PythonW = $pyw; Version = $ver }
    }
    $good = @($found | Where-Object { $_.Version -ge [version]'3.10' -and $_.Version -lt [version]'3.14' } | Sort-Object Version -Descending)
    $rest = @($found | Where-Object { -not ($_.Version -ge [version]'3.10' -and $_.Version -lt [version]'3.14') } | Sort-Object Version -Descending)
    $all = @($good) + @($rest)
    # one entry per major.minor
    $seen = @{}
    $uniq = @()
    foreach ($f in $all) { $k = "$($f.Version)"; if (-not $seen.ContainsKey($k)) { $seen[$k] = 1; $uniq += $f } }
    return $uniq
}

function Find-AGFOPython {
    $all = @(Find-AGFOPythons)
    if ($all.Count) { return $all[0] }
    return $null
}
