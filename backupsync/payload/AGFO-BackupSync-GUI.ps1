#requires -Version 5.1
# AGFO BackupSync v2 - native Windows Forms interface (AGFO dark theme).
$ErrorActionPreference = 'Stop'

# v2.3.1: The tray app is a PyInstaller onefile exe. Its private variables (_PYI_*, _MEIPASS2)
# leaked through PowerShell into AGFO-BackupSync.exe helper calls, which then tried to load
# python312.dll from another _MEI folder ("Failed to load Python DLL"). Clean them for every child.
function Clear-AgfoFrozenEnvironment {
    foreach ($key in @([Environment]::GetEnvironmentVariables('Process').Keys)) {
        $name = [string]$key
        if ($name -like '_PYI_*' -or $name -like '_MEIPASS*') {
            [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        }
    }
    [Environment]::SetEnvironmentVariable('PYINSTALLER_RESET_ENVIRONMENT', '1', 'Process')
    try {
        if (-not ('AgfoNative.DllPath' -as [type])) {
            Add-Type -Namespace AgfoNative -Name DllPath -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode, SetLastError = true)]
public static extern bool SetDllDirectoryW(string lpPathName);
'@
        }
        [void][AgfoNative.DllPath]::SetDllDirectoryW($null)
    } catch { }
}
function Set-AgfoHelperEnvironment([System.Diagnostics.ProcessStartInfo]$Psi) {
    $names = @($Psi.EnvironmentVariables.Keys | ForEach-Object { [string]$_ } |
        Where-Object { $_ -like '_PYI_*' -or $_ -like '_MEIPASS*' })
    foreach ($name in $names) { $Psi.EnvironmentVariables.Remove($name) }
    $Psi.EnvironmentVariables['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
}
Clear-AgfoFrozenEnvironment
. (Join-Path $PSScriptRoot 'AGFO-BackupSync-Core.ps1')
Initialize-Agfo
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$script:CurrentProfileFile = ''
$script:ApplyingProfile = $false
$script:LiveProcess = $null
$script:LiveLog = ''
$script:LiveStatus = ''
$script:LiveCancel = ''
$script:LastLog = ''
$script:InstallProcess = $null
$script:DiscoveryProcess = $null
$script:DiscoveryFile = ''
$script:DiscoveryMode = ''
$script:DiscoveryStarted = [DateTime]::MinValue
$script:ProbeListItem = $null
$script:DriveProcess = $null
$script:DriveFile = ''
$script:DriveAction = ''
$script:DriveStarted = [DateTime]::MinValue

# AGFO standard dark palette (same as System Care / SuperTools). Never dark text on dark.
$bgColor = [System.Drawing.Color]::FromArgb(10, 20, 37)          # #0a1425
$panelColor = [System.Drawing.Color]::FromArgb(18, 36, 59)       # #12243b
$panel2Color = [System.Drawing.Color]::FromArgb(25, 46, 72)      # #192e48
$inputColor = [System.Drawing.Color]::FromArgb(14, 28, 48)
$borderColor = [System.Drawing.Color]::FromArgb(45, 74, 108)
$hoverColor = [System.Drawing.Color]::FromArgb(36, 64, 98)
$fgColor = [System.Drawing.Color]::FromArgb(236, 243, 255)       # #ecf3ff
$mutedColor = [System.Drawing.Color]::FromArgb(165, 182, 206)    # #a5b6ce
$accentColor = [System.Drawing.Color]::FromArgb(73, 179, 239)    # #49b3ef
$primaryColor = [System.Drawing.Color]::FromArgb(31, 111, 163)
$warnColor = [System.Drawing.Color]::FromArgb(226, 179, 86)      # #e2b356
$okColor = [System.Drawing.Color]::FromArgb(111, 211, 155)       # #6fd39b
$logBackColor = [System.Drawing.Color]::FromArgb(7, 15, 28)
$mainColor = $fgColor
$surfaceColor = $bgColor
$brandFont = [System.Drawing.Font]::new('Segoe UI', 8, [System.Drawing.FontStyle]::Bold)
$normalFont = [System.Drawing.Font]::new('Segoe UI', 9)
$boldFont = [System.Drawing.Font]::new('Segoe UI', 9, [System.Drawing.FontStyle]::Bold)
$bigFont = [System.Drawing.Font]::new('Segoe UI', 16, [System.Drawing.FontStyle]::Bold)

$form = New-Object System.Windows.Forms.Form
$form.Text = 'AGFO BackupSync v2.3.1 | Windows / NAS'
$form.Size = [System.Drawing.Size]::new(1220, 820)
$form.MinimumSize = [System.Drawing.Size]::new(1220, 820)
$form.MaximumSize = [System.Drawing.Size]::new(1220, 820)
$form.StartPosition = 'CenterScreen'
$form.BackColor = $surfaceColor
$form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::Dpi
$form.Font = $normalFont
$form.ForeColor = $fgColor

# <AGFO-THEME-CS> Dark tab strip (native TabControl ignores BackColor). CI compiles this block.
$script:AgfoThemeSource = @'
using System;
using System.Drawing;
using System.Windows.Forms;
namespace AgfoUi {
    public class DarkTabControl : TabControl {
        public Color StripColor = Color.FromArgb(10, 20, 37);
        public Color TabColor = Color.FromArgb(25, 46, 72);
        public Color SelectedColor = Color.FromArgb(18, 36, 59);
        public Color TextColor = Color.FromArgb(236, 243, 255);
        public Color MutedTextColor = Color.FromArgb(165, 182, 206);
        public Color AccentColor = Color.FromArgb(73, 179, 239);
        public DarkTabControl() {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint |
                     ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            SizeMode = TabSizeMode.Fixed;
            ItemSize = new Size(146, 30);
        }
        protected override void OnPaint(PaintEventArgs e) {
            e.Graphics.Clear(StripColor);
            for (int i = 0; i < TabCount; i++) {
                Rectangle r = GetTabRect(i);
                bool selected = (i == SelectedIndex);
                using (SolidBrush b = new SolidBrush(selected ? SelectedColor : TabColor)) { e.Graphics.FillRectangle(b, r); }
                if (selected) {
                    using (SolidBrush a = new SolidBrush(AccentColor)) { e.Graphics.FillRectangle(a, r.X, r.Bottom - 3, r.Width, 3); }
                }
                TextRenderer.DrawText(e.Graphics, TabPages[i].Text, Font, r, selected ? TextColor : MutedTextColor,
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter |
                    TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis);
            }
        }
    }
}
'@
# </AGFO-THEME-CS>
function New-AgfoTabControl {
    try {
        if (-not ('AgfoUi.DarkTabControl' -as [type])) {
            Add-Type -TypeDefinition $script:AgfoThemeSource -ReferencedAssemblies System.Windows.Forms, System.Drawing
        }
        return (New-Object AgfoUi.DarkTabControl)
    } catch {
        # Fallback: owner-drawn headers on the standard control (all features unchanged).
        $t = New-Object System.Windows.Forms.TabControl
        $t.DrawMode = [System.Windows.Forms.TabDrawMode]::OwnerDrawFixed
        $t.SizeMode = [System.Windows.Forms.TabSizeMode]::Fixed
        $t.ItemSize = [System.Drawing.Size]::new(146, 30)
        $t.add_DrawItem({
            param($sender, $e)
            $selected = ($e.Index -eq $sender.SelectedIndex)
            $back = if ($selected) { $panelColor } else { $panel2Color }
            $brush = New-Object System.Drawing.SolidBrush $back
            try { $e.Graphics.FillRectangle($brush, $e.Bounds) } finally { $brush.Dispose() }
            $fore = if ($selected) { $fgColor } else { $mutedColor }
            [System.Windows.Forms.TextRenderer]::DrawText($e.Graphics, $sender.TabPages[$e.Index].Text, $sender.Font,
                $e.Bounds, $fore, ([System.Windows.Forms.TextFormatFlags]::HorizontalCenter -bor
                [System.Windows.Forms.TextFormatFlags]::VerticalCenter -bor [System.Windows.Forms.TextFormatFlags]::SingleLine))
        })
        return $t
    }
}
function Set-AgfoListTheme($List) {
    $List.BackColor = $inputColor
    $List.ForeColor = $fgColor
    $List.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    if ($List -is [System.Windows.Forms.ListView]) {
        $List.GridLines = $false
        $List.OwnerDraw = $true
        $List.add_DrawColumnHeader({
            param($sender, $e)
            $brush = New-Object System.Drawing.SolidBrush $panel2Color
            $pen = New-Object System.Drawing.Pen $borderColor
            try {
                $e.Graphics.FillRectangle($brush, $e.Bounds)
                $e.Graphics.DrawLine($pen, $e.Bounds.Right - 1, $e.Bounds.Top + 4, $e.Bounds.Right - 1, $e.Bounds.Bottom - 4)
                $e.Graphics.DrawLine($pen, $e.Bounds.Left, $e.Bounds.Bottom - 1, $e.Bounds.Right, $e.Bounds.Bottom - 1)
            } finally { $brush.Dispose(); $pen.Dispose() }
            $r = [System.Drawing.Rectangle]::new($e.Bounds.X + 6, $e.Bounds.Y, $e.Bounds.Width - 8, $e.Bounds.Height)
            [System.Windows.Forms.TextRenderer]::DrawText($e.Graphics, $e.Header.Text, $boldFont, $r, $fgColor,
                ([System.Windows.Forms.TextFormatFlags]::VerticalCenter -bor [System.Windows.Forms.TextFormatFlags]::Left -bor
                [System.Windows.Forms.TextFormatFlags]::SingleLine -bor [System.Windows.Forms.TextFormatFlags]::EndEllipsis))
        })
        $List.add_DrawItem({ param($sender, $e) $e.DrawDefault = $true })
        $List.add_DrawSubItem({ param($sender, $e) $e.DrawDefault = $true })
    }
}
function Set-AgfoGroupTheme($Group) {
    $Group.ForeColor = $accentColor
    $Group.BackColor = $panelColor
}
function New-AgfoTabPage([string]$Title) {
    $page = New-Object System.Windows.Forms.TabPage
    $page.Text = $Title
    $page.BackColor = $panelColor
    $page.ForeColor = $fgColor
    $page.Font = $normalFont
    return $page
}

function UiLabel($Parent, [string]$Title, [int]$X, [int]$Y, [int]$W, [int]$H, [bool]$Bold = $false) {
    $c = New-Object System.Windows.Forms.Label
    $c.Text = $Title
    $c.Location = [System.Drawing.Point]::new($X, $Y)
    $c.Size = [System.Drawing.Size]::new($W, $H)
    $c.ForeColor = $fgColor
    $c.BackColor = [System.Drawing.Color]::Transparent
    if ($Bold) { $c.Font = $boldFont }
    $Parent.Controls.Add($c)
    return $c
}
function UiText($Parent, [int]$X, [int]$Y, [int]$W, [int]$H = 25) {
    $c = New-Object System.Windows.Forms.TextBox
    $c.Location = [System.Drawing.Point]::new($X, $Y)
    $c.Size = [System.Drawing.Size]::new($W, $H)
    $c.BackColor = $inputColor
    $c.ForeColor = $fgColor
    $c.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $Parent.Controls.Add($c)
    return $c
}
function UiButton($Parent, [string]$Title, [int]$X, [int]$Y, [int]$W, [int]$H = 32) {
    $c = New-Object System.Windows.Forms.Button
    $c.Text = $Title
    $c.Location = [System.Drawing.Point]::new($X, $Y)
    $c.Size = [System.Drawing.Size]::new($W, $H)
    $c.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $c.BackColor = $panel2Color
    $c.ForeColor = $fgColor
    $c.FlatAppearance.BorderColor = $borderColor
    $c.FlatAppearance.MouseOverBackColor = $hoverColor
    $c.FlatAppearance.MouseDownBackColor = $primaryColor
    $c.UseVisualStyleBackColor = $false
    $c.Cursor = [System.Windows.Forms.Cursors]::Hand
    $Parent.Controls.Add($c)
    return $c
}
function UiCombo($Parent, [int]$X, [int]$Y, [int]$W, [string[]]$Options) {
    $c = New-Object System.Windows.Forms.ComboBox
    $c.Location = [System.Drawing.Point]::new($X, $Y)
    $c.Size = [System.Drawing.Size]::new($W, 27)
    $c.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
    $c.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $c.BackColor = $inputColor
    $c.ForeColor = $fgColor
    foreach ($option in $Options) { [void]$c.Items.Add($option) }
    $c.SelectedIndex = 0
    $Parent.Controls.Add($c)
    return $c
}
function UiNumeric($Parent, [int]$X, [int]$Y, [int]$Min, [int]$Max, [int]$Default, [int]$W = 68) {
    $c = New-Object System.Windows.Forms.NumericUpDown
    $c.Location = [System.Drawing.Point]::new($X, $Y)
    $c.Size = [System.Drawing.Size]::new($W, 27)
    $c.Minimum = $Min
    $c.Maximum = $Max
    $c.Value = $Default
    $c.BackColor = $inputColor
    $c.ForeColor = $fgColor
    $c.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $Parent.Controls.Add($c)
    return $c
}
function UiCheck($Parent, [string]$Title, [int]$X, [int]$Y, [int]$W, [bool]$Value = $false) {
    $c = New-Object System.Windows.Forms.CheckBox
    $c.Text = $Title
    $c.Location = [System.Drawing.Point]::new($X, $Y)
    $c.Size = [System.Drawing.Size]::new($W, 27)
    $c.Checked = $Value
    $c.ForeColor = $fgColor
    $c.BackColor = [System.Drawing.Color]::Transparent
    $Parent.Controls.Add($c)
    return $c
}
function Notice([string]$Message, [string]$Caption = 'AGFO BackupSync', [string]$Kind = 'Information') {
    $icon = [System.Enum]::Parse([System.Windows.Forms.MessageBoxIcon], $Kind)
    [void][System.Windows.Forms.MessageBox]::Show($form, $Message, $Caption,
        [System.Windows.Forms.MessageBoxButtons]::OK, $icon)
}
function Confirm([string]$Message, [string]$Caption = 'Onay') {
    return ([System.Windows.Forms.MessageBox]::Show($form, $Message, $Caption,
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning) -eq [System.Windows.Forms.DialogResult]::Yes)
}
function Show-FolderBrowser([System.Windows.Forms.TextBox]$Textbox) {
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    try {
        $dlg.Description = 'Klasor secin. SMB paylasimlarini kutuya \\NAS\Paylasim olarak da yazabilirsiniz.'
        if ([System.IO.Directory]::Exists($Textbox.Text)) { $dlg.SelectedPath = $Textbox.Text }
        if ($dlg.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) { $Textbox.Text = $dlg.SelectedPath }
    } finally { $dlg.Dispose() }
}

$header = New-Object System.Windows.Forms.Panel
$header.Location = [System.Drawing.Point]::new(0, 0)
$header.Size = [System.Drawing.Size]::new(1220, 80)
$header.BackColor = $panelColor
$form.Controls.Add($header)
$brand = UiLabel $header 'AGFO  /  SUPERTOOLS' 27 8 400 16 $true
$brand.Font = $brandFont
$brand.ForeColor = $accentColor
$heading = UiLabel $header 'AGFO BackupSync' 26 23 700 32 $true
$heading.Font = $bigFont
$heading.ForeColor = $fgColor
$subheading = UiLabel $header 'Windows 11 | NAS yedekleme | Sürüm arşivi | Gece zamanlaması' 27 55 950 20
$subheading.ForeColor = $mutedColor
$headerVersion = UiLabel $header 'v2.3.1' 1090 30 100 22 $true
$headerVersion.ForeColor = $accentColor
$headerVersion.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
$headerLine = New-Object System.Windows.Forms.Panel
$headerLine.Location = [System.Drawing.Point]::new(0, 78)
$headerLine.Size = [System.Drawing.Size]::new(1220, 2)
$headerLine.BackColor = $accentColor
$header.Controls.Add($headerLine)

$sidebar = New-Object System.Windows.Forms.GroupBox
$sidebar.Text = 'Yedekleme profilleri'
$sidebar.Location = [System.Drawing.Point]::new(14, 92)
$sidebar.Size = [System.Drawing.Size]::new(249, 651)
Set-AgfoGroupTheme $sidebar
$form.Controls.Add($sidebar)
$listProfiles = New-Object System.Windows.Forms.ListBox
$listProfiles.Location = [System.Drawing.Point]::new(12, 33)
$listProfiles.Size = [System.Drawing.Size]::new(224, 358)
$listProfiles.DisplayMember = 'Name'
Set-AgfoListTheme $listProfiles
$listProfiles.Font = $normalFont
$sidebar.Controls.Add($listProfiles)
$btnNew = UiButton $sidebar 'Yeni' 12 407 105
$btnDuplicate = UiButton $sidebar 'Çoğalt' 128 407 108
$btnSave = UiButton $sidebar 'Profili kaydet' 12 450 224 37
$btnDelete = UiButton $sidebar 'Profili sil' 12 500 105
$btnImport = UiButton $sidebar 'v1 profillerini al' 12 547 224 34
$sidebarNote = UiLabel $sidebar 'İşler birbirinden bağımsızdır. Parolalar saklanmaz. Uzak NAS için UNC yolu kullanın.' 12 594 218 47
$sidebarNote.ForeColor = $mutedColor

$tabs = New-AgfoTabControl
$tabs.Font = $normalFont
$tabs.Location = [System.Drawing.Point]::new(276, 92)
$tabs.Size = [System.Drawing.Size]::new(927, 651)
$form.Controls.Add($tabs)
$tabBackup = New-AgfoTabPage 'Yedekleme / Eşitleme'
$tabs.TabPages.Add($tabBackup)
$tabSchedule = New-AgfoTabPage 'Gece Zamanlaması'
$tabs.TabPages.Add($tabSchedule)
$tabVersions = New-AgfoTabPage 'Sürümler / Geri Yükle'
$tabs.TabPages.Add($tabVersions)
$tabLogs = New-AgfoTabPage 'Kayıtlar / Motorlar'
$tabs.TabPages.Add($tabLogs)
$tabNetwork = New-AgfoTabPage 'Ag Kesfi / SMB'
$tabs.TabPages.Add($tabNetwork)

$tabDrives = New-AgfoTabPage 'Surucu Harfleri'
$tabs.TabPages.Add($tabDrives)

# TAB 1 - transfer settings
[void](UiLabel $tabBackup 'Profil adı' 18 13 125 22 $true)
$txtName = UiText $tabBackup 149 10 699
[void](UiLabel $tabBackup 'Kaynak klasör' 18 48 125 22 $true)
$txtSource = UiText $tabBackup 149 45 605
$btnPickSource = UiButton $tabBackup 'Seç...' 763 43 85
[void](UiLabel $tabBackup 'Hedef klasör' 18 84 125 22 $true)
$txtTarget = UiText $tabBackup 149 81 605
$btnPickTarget = UiButton $tabBackup 'Seç...' 763 79 85

[void](UiLabel $tabBackup 'Çalışma modu' 18 125 125 25 $true)
$cmbMode = UiCombo $tabBackup 149 123 699 @(
    'Artımlı yedek - Robocopy (silmez, eski sürümü saklamaz)',
    'Sürümlü yedek - rclone (değişen eski dosyaları arşivler)',
    'Sürümlü eşitleme - rclone (hedeften eksilenleri arşivler)')
[void](UiLabel $tabBackup 'Kopyalama kuralı' 18 165 132 22)
$cmbRule = UiCombo $tabBackup 149 162 341 @(
    'Eksikleri ve değişenleri kopyala',
    'Yalnızca hedefte eksik olanları',
    'Eksikleri ve kaynakta daha yenileri')
[void](UiLabel $tabBackup 'Eşitleme silme limiti' 516 164 162 22)
$numMaxDelete = UiNumeric $tabBackup 684 161 1 100000 100 83
[void](UiLabel $tabBackup 'dosya' 780 165 65 22)

[void](UiLabel $tabBackup 'Paralel aktarım' 18 207 119 22)
$numThreads = UiNumeric $tabBackup 150 203 1 32 8
[void](UiLabel $tabBackup 'Hata tekrar' 247 207 98 22)
$numRetry = UiNumeric $tabBackup 340 203 0 20 2
[void](UiLabel $tabBackup 'Tekrar bekleme (sn)' 453 207 154 22)
$numWait = UiNumeric $tabBackup 609 203 0 120 5
[void](UiLabel $tabBackup 'Hariç dosyalar' 18 247 120 22)
$txtExcludeFiles = UiText $tabBackup 149 243 699
[void](UiLabel $tabBackup 'Hariç klasörler' 18 283 121 22)
$txtExcludeDirs = UiText $tabBackup 149 280 699
[void](UiLabel $tabBackup 'Örnek: *.tmp;Thumbs.db | WindowsApps;System Volume Information;@eaDir' 149 308 708 22)
$chkNoSleep = UiCheck $tabBackup 'Çalışırken Windows uykuya geçmesin' 17 336 316 $true
$chkVerbose = UiCheck $tabBackup 'Ayrıntılı kayıt tut' 368 336 213
$chkMirror = UiCheck $tabBackup 'Hedefteki fazlaların sürüm arşivine taşınmasını ONAYLIYORUM' 17 370 839
$lblModeInfo = UiLabel $tabBackup 'Artımlı yedek: Hedefteki fazladan dosyalar silinmez. Güncellenen dosyaların eski hali saklanmaz.' 19 401 850 36
$lblModeInfo.ForeColor = $mutedColor

$btnTest = UiButton $tabBackup 'Bağlantı testi' 19 440 139 34
$btnPreview = UiButton $tabBackup 'Önizleme' 171 440 143 34
$btnRun = UiButton $tabBackup 'Şimdi çalıştır' 326 440 164 34
$btnRun.BackColor = $primaryColor
$btnRun.ForeColor = [System.Drawing.Color]::White
$btnRun.Font = $boldFont
$btnRun.FlatAppearance.BorderColor = $accentColor
$btnRun.FlatAppearance.MouseOverBackColor = [System.Drawing.Color]::FromArgb(40, 132, 190)
$btnStop = UiButton $tabBackup 'Durdur' 502 440 107 34
$btnStop.Enabled = $false
$btnOpenLast = UiButton $tabBackup 'Son logu aç' 622 440 133 34
$lblState = UiLabel $tabBackup 'Durum: Hazır' 18 480 855 25 $true
$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Location = [System.Drawing.Point]::new(19, 509)
$progress.Size = [System.Drawing.Size]::new(864, 12)
$tabBackup.Controls.Add($progress)
$txtLiveLog = New-Object System.Windows.Forms.TextBox
$txtLiveLog.Location = [System.Drawing.Point]::new(19, 529)
$txtLiveLog.Size = [System.Drawing.Size]::new(865, 84)
$txtLiveLog.Multiline = $true
$txtLiveLog.ReadOnly = $true
$txtLiveLog.ScrollBars = [System.Windows.Forms.ScrollBars]::Vertical
$txtLiveLog.Font = [System.Drawing.Font]::new('Consolas', 8)
$txtLiveLog.BackColor = $logBackColor
$txtLiveLog.ForeColor = [System.Drawing.Color]::FromArgb(200, 222, 242)
$txtLiveLog.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$tabBackup.Controls.Add($txtLiveLog)

# TAB 2 - Task Scheduler
[void](UiLabel $tabSchedule 'Windows Görev Zamanlayıcı ile gece otomatik yedekleme' 25 25 821 32 $true)
[void](UiLabel $tabSchedule 'Sıklık' 27 86 115 22)
$cmbSchedule = UiCombo $tabSchedule 179 83 245 @('Her gün', 'Haftada bir')
[void](UiLabel $tabSchedule 'Gün' 480 86 70 22)
$cmbDay = UiCombo $tabSchedule 551 83 189 @('Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar')
[void](UiLabel $tabSchedule 'Saat' 27 141 117 22)
$pickerTime = New-Object System.Windows.Forms.DateTimePicker
$pickerTime.Location = [System.Drawing.Point]::new(179, 137)
$pickerTime.Size = [System.Drawing.Size]::new(149, 28)
$pickerTime.Format = [System.Windows.Forms.DateTimePickerFormat]::Custom
$pickerTime.CustomFormat = 'HH:mm'
$pickerTime.ShowUpDown = $true
$pickerTime.Value = [DateTime]::Today.AddHours(2)
$tabSchedule.Controls.Add($pickerTime)
$chkWake = UiCheck $tabSchedule 'Zamanı geldiğinde bilgisayarı uyandırmayı dene' 27 200 780 $true
$chkBattery = UiCheck $tabSchedule 'Dizüstü pildeyken de çalışsın' 27 241 780
$chkTaskRetry = UiCheck $tabSchedule 'Hata olursa 15 dakika arayla 2 kez daha dene' 27 275 780 $true
$btnSchedule = UiButton $tabSchedule 'Görevi oluştur / güncelle' 26 334 243 38
$btnUnschedule = UiButton $tabSchedule 'Görevi kaldır' 283 334 167 38
$btnScheduleStatus = UiButton $tabSchedule 'Durumu sorgula' 463 334 161 38
$lblScheduleState = UiLabel $tabSchedule 'Görev durumu henüz sorgulanmadı.' 27 397 820 78
$lblScheduleState.ForeColor = $mutedColor
[void](UiLabel $tabSchedule 'Zamanlanmış işler oturum AÇIKKEN çalışır; ekran kilitli olabilir. Oturumu kapatmayın.' 27 482 825 26 $true)
[void](UiLabel $tabSchedule 'Ağ disk harfleri yerine \\NAS\Paylasim biçiminde UNC yolunu kullanın. Parola uygulamada tutulmaz.' 27 514 830 50)
[void](UiLabel $tabSchedule 'Zamanlanan görev GERÇEK aktarım yapar; Önizleme seçeneği zamanlamaya uygulanmaz.' 27 566 828 25)

# TAB 3 - archive/restore
[void](UiLabel $tabVersions 'Eski dosya sürümleri' 23 23 633 29 $true)
[void](UiLabel $tabVersions 'Sürüm arşivi yalnızca değişen / eşitlemede hedeften kaldırılan eski dosyaları içerir.' 23 55 850 31)
$listVersions = New-Object System.Windows.Forms.ListBox
$listVersions.Location = [System.Drawing.Point]::new(23, 97)
$listVersions.Size = [System.Drawing.Size]::new(850, 274)
$listVersions.DisplayMember = 'Name'
Set-AgfoListTheme $listVersions
$tabVersions.Controls.Add($listVersions)
$btnVersions = UiButton $tabVersions 'Arşivi yenile' 23 384 162 34
$btnOpenVersions = UiButton $tabVersions 'Sürüm klasörünü aç' 202 384 194 34
[void](UiLabel $tabVersions 'Geri yükleme hedefi: yeni, boş bir klasör yolu girin (canlı klasörlere yazılmaz).' 23 442 845 30)
$txtRestore = UiText $tabVersions 23 472 738
$btnRestorePick = UiButton $tabVersions 'Seç...' 773 470 101
$btnRestorePreview = UiButton $tabVersions 'Geri yükleme önizleme' 23 522 228 40
$btnRestore = UiButton $tabVersions 'Seçili sürümü geri yükle' 267 522 261 40
$lblRestoreInfo = UiLabel $tabVersions 'Geri yüklenen dosyalar seçtiğiniz yeni klasöre kopyalanır; mevcut yedeklere dokunulmaz.' 23 580 842 38
$lblRestoreInfo.ForeColor = $mutedColor

# TAB 4 - Logs / engine
[void](UiLabel $tabLogs 'Son çalıştırmalar / hata kayıtları' 23 19 781 30 $true)
$listLogs = New-Object System.Windows.Forms.ListBox
$listLogs.Location = [System.Drawing.Point]::new(23, 53)
$listLogs.Size = [System.Drawing.Size]::new(850, 293)
$listLogs.DisplayMember = 'Name'
Set-AgfoListTheme $listLogs
$tabLogs.Controls.Add($listLogs)
$btnLogRefresh = UiButton $tabLogs 'Listeyi yenile' 23 359 143 35
$btnLogOpen = UiButton $tabLogs 'Seçili kaydı aç' 182 359 179 35
$btnLogFolder = UiButton $tabLogs 'Log klasörü' 376 359 153 35
$lblLastResult = UiLabel $tabLogs 'Son durum: -' 23 413 847 56
$lblLastResult.ForeColor = $mutedColor
$groupEngine = New-Object System.Windows.Forms.GroupBox
$groupEngine.Text = 'Aktarım motorları ve isteğe bağlı kurulum'
$groupEngine.Location = [System.Drawing.Point]::new(23, 473)
$groupEngine.Size = [System.Drawing.Size]::new(850, 128)
Set-AgfoGroupTheme $groupEngine
$tabLogs.Controls.Add($groupEngine)
$lblEngine = UiLabel $groupEngine 'Robocopy kontrol ediliyor; rclone isteğe bağlı.' 16 27 799 25
$btnInstall = UiButton $groupEngine 'rclone kur (winget)' 16 69 215 34
$btnEngineCheck = UiButton $groupEngine 'Motorları kontrol et' 248 69 212 34


# TAB 5 - network discovery; engine runs in a separate subprocess to avoid UI freezes.
[void](UiLabel $tabNetwork 'Windows suruculeri ve yerel SMB agi' 23 16 850 28 $true)
[void](UiLabel $tabNetwork 'Bagli ag suruculeri otomatik listelenir. "SMB ara" sadece yerel ozel IPv4 /24 aglarini tarar.' 23 45 854 26)
$btnDiscoveryKnown = UiButton $tabNetwork 'Bagli suruculeri yenile' 23 80 206 37
$btnDiscoveryScan = UiButton $tabNetwork 'Yerel agda SMB ara' 243 80 193 37
$btnDiscoveryTest = UiButton $tabNetwork 'Secili yolu test et' 450 80 179 37
$btnDiscoveryBrowse = UiButton $tabNetwork 'Gezginde ac' 643 80 154 37
$listNetwork = New-Object System.Windows.Forms.ListView
$listNetwork.Location = [System.Drawing.Point]::new(23, 128)
$listNetwork.Size = [System.Drawing.Size]::new(850, 344)
$listNetwork.View = [System.Windows.Forms.View]::Details
$listNetwork.FullRowSelect = $true
$listNetwork.MultiSelect = $false
$listNetwork.HideSelection = $false
$listNetwork.GridLines = $true
[void]$listNetwork.Columns.Add('Tur', 142)
[void]$listNetwork.Columns.Add('Ad', 213)
[void]$listNetwork.Columns.Add('Yol', 328)
[void]$listNetwork.Columns.Add('Durum', 150)
Set-AgfoListTheme $listNetwork
$tabNetwork.Controls.Add($listNetwork)
$btnNetworkSource = UiButton $tabNetwork 'Kaynak olarak sec' 23 491 204 40
$btnNetworkTarget = UiButton $tabNetwork 'Hedef olarak sec' 240 491 204 40
$btnNetworkSubfolder = UiButton $tabNetwork 'Alt klasor sec...' 457 491 183 40
$btnNetworkToDrive = UiButton $tabNetwork 'Harfe bagla...' 665 491 191 40

$lblDiscovery = UiLabel $tabNetwork 'Bagli surucu listesi yukleniyor...' 23 549 850 64
$lblDiscovery.ForeColor = $mutedColor

# TAB 6 - non-destructive drive letter manager.
[void](UiLabel $tabDrives 'SMB ag paylasimi = NET USE  |  Yerel klasor = SUBST' 22 18 868 26 $true)
[void](UiLabel $tabDrives 'SMB: \\NAS\Paylasim\Klasor    |    Yerel: C:\Belgeler\Arsiv' 22 47 858 25)
[void](UiLabel $tabDrives 'Eslenmek istenen yol' 22 86 188 25)
$txtDrivePath = UiText $tabDrives 216 82 636
[void](UiLabel $tabDrives 'Bos surucu harfi' 22 130 172 26)
$cmbDriveLetter = UiCombo $tabDrives 216 125 100 @('Z:')
$chkDrivePersist = UiCheck $tabDrives 'Windows acilisinda SMB baglantisini yeniden kur' 330 126 510 $true
$btnDriveMap = UiButton $tabDrives 'Surucuye bagla' 22 173 194 38
$btnDriveUnmap = UiButton $tabDrives 'Secili eslemeyi kaldir' 232 173 220 38
$btnDriveRefresh = UiButton $tabDrives 'Suruculeri yenile' 468 173 191 38
$btnDriveBrowse = UiButton $tabDrives 'Gezginde ac' 675 173 177 38
$listDrives = New-Object System.Windows.Forms.ListView
$listDrives.Location = [System.Drawing.Point]::new(22, 225)
$listDrives.Size = [System.Drawing.Size]::new(830, 295)
$listDrives.View = [System.Windows.Forms.View]::Details
$listDrives.FullRowSelect = $true
$listDrives.MultiSelect = $false
$listDrives.HideSelection = $false
$listDrives.GridLines = $true
[void]$listDrives.Columns.Add('Harf', 81)
[void]$listDrives.Columns.Add('Yontem', 97)
[void]$listDrives.Columns.Add('Gercek yol', 424)
[void]$listDrives.Columns.Add('Durum', 215)
Set-AgfoListTheme $listDrives
$tabDrives.Controls.Add($listDrives)
$btnDriveSource = UiButton $tabDrives 'Kaynak olarak sec' 22 531 192 36
$btnDriveTarget = UiButton $tabDrives 'Hedef olarak sec' 228 531 192 36
$lblDriveStatus = UiLabel $tabDrives 'Surucu harfleri okunuyor...' 22 577 846 53
$lblDriveStatus.ForeColor = $mutedColor
[void](UiLabel $tabDrives 'Gece yedekleri esleme harfini degil, orijinal UNC/yerel yolu kullanir. SUBST yeniden baslatmada kaybolur.' 22 608 848 26)

$footer = UiLabel $form 'AGFO BackupSync v2.3.1  |  Tek yönlü aktarım  |  Şifre ve parola kaydedilmez  |  Kaynak dosyalar silinmez' 26 751 1150 31
$footer.ForeColor = $mutedColor

function Selected-ProfileItem { return $listProfiles.SelectedItem }
function Selected-ProfilePath {
    $item = Selected-ProfileItem
    if ($null -eq $item) { throw 'Önce bir yedekleme profili seçin.' }
    return [string]$item.Path
}
function Selected-Profile {
    return (Read-AgfoProfile (Selected-ProfilePath))
}
function Get-UiProfile {
    $p = Selected-Profile
    $p.profileName = $txtName.Text.Trim()
    $p.source = $txtSource.Text.Trim()
    $p.target = $txtTarget.Text.Trim()
    $p.mode = switch ($cmbMode.SelectedIndex) { 1 { 'versioned' } 2 { 'mirror' } default { 'incremental' } }
    $p.copyRule = switch ($cmbRule.SelectedIndex) { 1 { 'missing' } 2 { 'newer' } default { 'update' } }
    $p.threads = [int]$numThreads.Value
    $p.retries = [int]$numRetry.Value
    $p.waitSeconds = [int]$numWait.Value
    $p.maxDelete = [int]$numMaxDelete.Value
    $p.excludeFiles = $txtExcludeFiles.Text
    $p.excludeDirs = $txtExcludeDirs.Text
    $p.preventSleep = [bool]$chkNoSleep.Checked
    $p.verboseLog = [bool]$chkVerbose.Checked
    $p.mirrorConsent = [bool]$chkMirror.Checked
    $p.scheduleTime = $pickerTime.Value.ToString('HH:mm')
    $p.scheduleKind = if ($cmbSchedule.SelectedIndex -eq 1) { 'weekly' } else { 'daily' }
    $p.scheduleDay = @('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')[[Math]::Max(0, $cmbDay.SelectedIndex)]
    $p.scheduleWake = [bool]$chkWake.Checked
    $p.scheduleBattery = [bool]$chkBattery.Checked
    $p.scheduleRetry = [bool]$chkTaskRetry.Checked
    return $p
}
function Apply-UiProfile([object]$P) {
    $script:ApplyingProfile = $true
    try {
        $txtName.Text = [string]$P.profileName
        $txtSource.Text = [string]$P.source
        $txtTarget.Text = [string]$P.target
        $cmbMode.SelectedIndex = switch ([string]$P.mode) { 'versioned' { 1 } 'mirror' { 2 } default { 0 } }
        $cmbRule.SelectedIndex = switch ([string]$P.copyRule) { 'missing' { 1 } 'newer' { 2 } default { 0 } }
        $numThreads.Value = [Math]::Max(1, [Math]::Min(32, [decimal]$P.threads))
        $numRetry.Value = [Math]::Max(0, [Math]::Min(20, [decimal]$P.retries))
        $numWait.Value = [Math]::Max(0, [Math]::Min(120, [decimal]$P.waitSeconds))
        $numMaxDelete.Value = [Math]::Max(1, [Math]::Min(100000, [decimal]$P.maxDelete))
        $txtExcludeFiles.Text = [string]$P.excludeFiles
        $txtExcludeDirs.Text = [string]$P.excludeDirs
        $chkNoSleep.Checked = [bool]$P.preventSleep
        $chkVerbose.Checked = [bool]$P.verboseLog
        $chkMirror.Checked = [bool]$P.mirrorConsent
        if ([string]$P.scheduleTime -match '^([0-2]?[0-9]):([0-5][0-9])$') {
            $hours = [Math]::Min(23, [int]$Matches[1])
            $pickerTime.Value = [DateTime]::Today.AddHours($hours).AddMinutes([int]$Matches[2])
        }
        $cmbSchedule.SelectedIndex = if ([string]$P.scheduleKind -eq 'weekly') { 1 } else { 0 }
        $days = @('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')
        $idx = [Array]::IndexOf($days, [string]$P.scheduleDay)
        $cmbDay.SelectedIndex = if ($idx -ge 0) { $idx } else { 0 }
        $chkWake.Checked = [bool]$P.scheduleWake
        $chkBattery.Checked = [bool]$P.scheduleBattery
        $chkTaskRetry.Checked = [bool]$P.scheduleRetry
        Update-ModeUi
        $lblState.Text = 'Durum: Profil yüklendi.'
    } finally { $script:ApplyingProfile = $false }
}
function Update-ModeUi {
    $mirror = ($cmbMode.SelectedIndex -eq 2)
    $numMaxDelete.Enabled = $mirror
    $chkMirror.Enabled = $mirror
    $cmbRule.Enabled = -not $mirror
    if ($mirror) {
        $lblModeInfo.Text = 'EŞİTLEME: Hedef fazlaları .agfo-versions arşivine alınır. Silme üst sınırı vardır. Kaynak boşsa işlem engellenir.'
        $lblModeInfo.ForeColor = $warnColor
    } elseif ($cmbMode.SelectedIndex -eq 1) {
        $lblModeInfo.Text = 'Sürümlü yedek: Güncellenecek eski hedef dosyaları .agfo-versions arşivinde tutulur. Hedef fazlaları korunur.'
        $lblModeInfo.ForeColor = $mutedColor
    } else {
        $lblModeInfo.Text = 'Artımlı yedek: Hedef fazlaları korunur; değişen hedef dosyasının eski sürümü saklanmaz.'
        $lblModeInfo.ForeColor = $mutedColor
    }
}
function Refresh-ProfileList([string]$ChooseId = '') {
    $listProfiles.Items.Clear()
    $items = @(Get-AgfoProfiles)
    foreach ($item in $items) { [void]$listProfiles.Items.Add($item) }
    if ($items.Count -eq 0) { return }
    if (-not $ChooseId -and [System.IO.File]::Exists($script:AgfoLast)) {
        $ChooseId = [System.IO.File]::ReadAllText($script:AgfoLast).Trim()
    }
    $selected = 0
    for ($i = 0; $i -lt $items.Count; $i++) {
        if ($items[$i].Id -eq $ChooseId) { $selected = $i; break }
    }
    $listProfiles.SelectedIndex = $selected
}
function Save-UiProfile {
    $p = Get-UiProfile
    $path = Save-AgfoProfile $p
    [System.IO.File]::WriteAllText($script:AgfoLast, [string]$p.profileId)
    Refresh-ProfileList ([string]$p.profileId)
    return $path
}
function Engine-Ready {
    $rob = Find-AgfoExe 'robocopy.exe'
    $rclone = Find-AgfoExe 'rclone.exe'
    $lblEngine.Text = ('Robocopy: ' + $(if ($rob) { 'Hazır' } else { 'Yok' }) +
        '     |     rclone: ' + $(if ($rclone) { 'Hazır' } else { 'Kurulu değil' }))
}
function Refresh-LogList {
    $listLogs.Items.Clear()
    $files = @(Get-ChildItem -LiteralPath $script:AgfoLogs -Filter '*.result.json' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 120)
    foreach ($file in $files) {
        try {
            $r = Read-AgfoJson $file.FullName
            $name = $file.LastWriteTime.ToString('dd.MM.yyyy HH:mm') + ' | ' +
                [string]$r.state + ' | ' + [string]$r.name +
                $(if ([bool]$r.preview) { ' [ÖNİZLEME]' } else { '' })
            [void]$listLogs.Items.Add([pscustomobject]@{ Name = $name; Path = [string]$r.log; Result = $file.FullName })
        } catch { }
    }
    if ($listLogs.Items.Count -gt 0) {
        try {
            $r = Read-AgfoJson $listLogs.Items[0].Result
            $lblLastResult.Text = ('Son iş: ' + [string]$r.state + ' | ' + [string]$r.message)
            $script:LastLog = [string]$r.log
        } catch { }
    }
}
function Refresh-VersionList {
    $listVersions.Items.Clear()
    $txtRestore.Text = ''
    if (-not (Selected-ProfileItem)) { return }
    $p = Selected-Profile
    $root = Get-AgfoArchiveRoot $p
    if (-not [System.IO.Directory]::Exists($root)) { return }
    $dirs = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction Stop | Sort-Object Name -Descending)
    foreach ($dir in $dirs) {
        [void]$listVersions.Items.Add([pscustomobject]@{ Name = $dir.Name; Path = $dir.FullName })
    }
    if ($listVersions.Items.Count -gt 0) { $listVersions.SelectedIndex = 0 }
}
function Refresh-RestoreSuggestion {
    $item = $listVersions.SelectedItem
    if (-not $item) { return }
    $p = Selected-Profile
    $folder = Join-Path $env:USERPROFILE 'Documents\AGFO-Restore'
    $txtRestore.Text = Join-Path $folder (([string]$p.profileId).Substring(0, 8) + '_' + [string]$item.Name)
}
function Open-LocalFile([string]$Path) {
    if (-not [System.IO.File]::Exists($Path)) { Notice 'Seçilen dosya bulunamadı.'; return }
    Start-Process -FilePath 'notepad.exe' -ArgumentList (Quote-AgfoArg $Path)
}
function Set-RunState([bool]$Running) {
    $btnRun.Enabled = -not $Running
    $btnPreview.Enabled = -not $Running
    $btnRestore.Enabled = -not $Running
    $btnRestorePreview.Enabled = -not $Running
    $btnStop.Enabled = $Running
    if ($Running) {
        $progress.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
        $progress.MarqueeAnimationSpeed = 20
    } else {
        $progress.MarqueeAnimationSpeed = 0
        $progress.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous
        $progress.Value = 0
    }
}
function Start-UiJob([bool]$Preview = $false, [string]$RestoreRun = '', [string]$RestoreTarget = '') {
    if ($script:LiveProcess -and -not $script:LiveProcess.HasExited) { throw 'Zaten bir işlem çalışıyor.' }
    $profilePath = Save-UiProfile
    $p = Read-AgfoProfile $profilePath
    if (($RestoreRun -or ([string]$p.mode -ne 'incremental')) -and -not (Find-AgfoExe 'rclone.exe')) {
        $tabs.SelectedTab = $tabLogs
        $btnInstall.PerformClick()
        return
    }
    if ($RestoreRun) {
        $null = New-AgfoRestoreCommand $p $RestoreRun $RestoreTarget 'C:\agfo-test.log' $Preview
    } else {
        $paths = Validate-AgfoPaths $p $true (-not $Preview)
        $null = New-AgfoEngineCommand $p $paths 'C:\agfo-test.log' 'validation' $Preview
    }
    if (([string]$p.mode -eq 'mirror') -and -not $Preview -and -not $RestoreRun) {
        $warning = 'Bu eşitleme, kaynakta olmayan hedef dosyalarını arşive taşıyacaktır.' + [Environment]::NewLine +
            'Silme limiti: ' + [string]$p.maxDelete + [Environment]::NewLine +
            'Arşiv: ' + (Get-AgfoArchiveRoot $p) + [Environment]::NewLine +
            'Önce Önizleme çalıştırılması önerilir. Devam edilsin mi?'
        if (-not (Confirm $warning 'Sürümlü eşitlemeyi onayla')) { return }
    }
    $id = (Get-Date -Format 'yyyyMMdd_HHmmss_fff') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 6)
    $script:LiveLog = Join-Path $script:AgfoLogs ($id + '.log')
    $script:LiveStatus = Join-Path $script:AgfoLogs ($id + '.result.json')
    $script:LiveCancel = $script:LiveStatus + '.cancel'
    if ([System.IO.File]::Exists($script:LiveCancel)) { [System.IO.File]::Delete($script:LiveCancel) }
    $worker = Join-Path $PSScriptRoot 'AGFO-BackupSync-Worker.ps1'
    $powershell = Join-Path $PSHOME 'powershell.exe'
    $args = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $worker,
        '-ProfilePath', $profilePath, '-LogPath', $script:LiveLog,
        '-StatusPath', $script:LiveStatus, '-CancelPath', $script:LiveCancel)
    if ($Preview) { $args += '-Preview' }
    if ($RestoreRun) { $args += @('-RestoreRun', $RestoreRun, '-RestoreTarget', $RestoreTarget) }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $powershell
    $psi.Arguments = Join-AgfoArgs $args
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $script:LiveProcess = New-Object System.Diagnostics.Process
    $script:LiveProcess.StartInfo = $psi
    if (-not $script:LiveProcess.Start()) { throw 'Arka plan işçisi başlatılamadı.' }
    $txtLiveLog.Clear()
    $lblState.Text = if ($Preview) { 'Durum: Önizleme çalışıyor...' } else { 'Durum: İşlem çalışıyor...' }
    Set-RunState $true
    $tabs.SelectedTab = $tabBackup
}
function Tail-UiLog {
    if (-not $script:LiveLog -or -not [System.IO.File]::Exists($script:LiveLog)) { return }
    try {
        $lines = @(Get-Content -LiteralPath $script:LiveLog -Tail 17 -ErrorAction Stop)
        $txtLiveLog.Text = ($lines -join [Environment]::NewLine)
        $txtLiveLog.SelectionStart = $txtLiveLog.TextLength
        $txtLiveLog.ScrollToCaret()
    } catch { }
}
function Get-AgfoTaskName([object]$P) { return ('AGFO-BackupSync-' + [string]$P.profileId) }
function Register-AgfoNightTask {
    $profilePath = Save-UiProfile
    $p = Read-AgfoProfile $profilePath
    $null = Validate-AgfoPaths $p $true
    if ([string]$p.mode -ne 'incremental' -and -not (Find-AgfoExe 'rclone.exe')) { throw 'Zamanlama öncesi rclone kurulmalıdır.' }
    if ([string]$p.mode -eq 'mirror' -and -not (Confirm ('Her çalışmada hedefte eksik olan dosyalar sürüm arşivine taşınacaktır. ' +
        'Bu riski kabul edip otomatik görevi oluşturmak istiyor musunuz?') 'Otomatik eşitleme uyarısı')) { return }
    $worker = Join-Path $PSScriptRoot 'AGFO-BackupSync-Worker.ps1'
    $psExe = Join-Path $PSHOME 'powershell.exe'
    $args = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $worker,
        '-ProfilePath', $profilePath)
    $action = New-ScheduledTaskAction -Execute $psExe -Argument (Join-AgfoArgs $args) -WorkingDirectory $PSScriptRoot
    $when = [DateTime]::Today.Add($pickerTime.Value.TimeOfDay)
    if ($cmbSchedule.SelectedIndex -eq 1) {
        $day = [System.Enum]::Parse([System.DayOfWeek], [string]$p.scheduleDay)
        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $day -At $when
    } else {
        $trigger = New-ScheduledTaskTrigger -Daily -At $when
    }
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $argsSettings = @{
        StartWhenAvailable = $true
        MultipleInstances = 'IgnoreNew'
        ExecutionTimeLimit = [TimeSpan]::Zero
    }
    if ($chkWake.Checked) { $argsSettings.WakeToRun = $true }
    if ($chkTaskRetry.Checked) {
        $argsSettings.RestartCount = 2
        $argsSettings.RestartInterval = (New-TimeSpan -Minutes 15)
    }
    if ($chkBattery.Checked) {
        $argsSettings.AllowStartIfOnBatteries = $true
        $argsSettings.DontStopIfGoingOnBatteries = $true
    }
    $settings = New-ScheduledTaskSettingsSet @argsSettings
    $name = Get-AgfoTaskName $p
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    $lblScheduleState.Text = ('Görev: ' + $name + [Environment]::NewLine +
        'Çalışma saati: ' + $when.ToString('HH:mm') + ' | Sıklık: ' + [string]$p.scheduleKind +
        ' | Kullanıcı: ' + [System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
}
function Check-AgfoTask {
    $p = Selected-Profile
    $name = Get-AgfoTaskName $p
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) { $lblScheduleState.Text = 'Bu profil için zamanlanmış görev bulunamadı.'; return }
    $details = $task | Get-ScheduledTaskInfo
    $lblScheduleState.Text = ('Görev: ' + $name + ' | Durum: ' + $task.State + [Environment]::NewLine +
        'Son sonuç: ' + $details.LastTaskResult + ' | Sonraki: ' + $details.NextRunTime)
}

$btnPickSource.Add_Click({ Show-FolderBrowser $txtSource })
$btnPickTarget.Add_Click({ Show-FolderBrowser $txtTarget })
$btnRestorePick.Add_Click({ Show-FolderBrowser $txtRestore })
$cmbMode.Add_SelectedIndexChanged({
    if (-not $script:ApplyingProfile) {
        if ($cmbMode.SelectedIndex -eq 2) { $cmbRule.SelectedIndex = 0 }
        $chkMirror.Checked = $false
    }
    Update-ModeUi
})
$cmbSchedule.Add_SelectedIndexChanged({ $cmbDay.Enabled = ($cmbSchedule.SelectedIndex -eq 1) })
$listProfiles.Add_SelectedIndexChanged({
    $item = $listProfiles.SelectedItem
    if ($item) {
        try {
            $script:CurrentProfileFile = [string]$item.Path
            Apply-UiProfile (Read-AgfoProfile $script:CurrentProfileFile)
            Refresh-VersionList
        } catch { Notice ([string]$_.Exception.Message) 'Profil yükleme hatası' 'Error' }
    }
})
$btnNew.Add_Click({
    try {
        $p = New-AgfoProfile
        $p.profileName = 'Yeni yedekleme ' + (Get-Date -Format 'HHmm')
        $null = Save-AgfoProfile $p
        Refresh-ProfileList ([string]$p.profileId)
    } catch { Notice ([string]$_.Exception.Message) 'Profil hatası' 'Error' }
})
$btnDuplicate.Add_Click({
    try {
        $p = Get-UiProfile
        $p.profileId = [guid]::NewGuid().ToString('N')
        $p.profileName += ' - kopya'
        $p.mirrorConsent = $false
        $p.importedFrom = ''
        $null = Save-AgfoProfile $p
        Refresh-ProfileList ([string]$p.profileId)
    } catch { Notice ([string]$_.Exception.Message) 'Çoğaltma hatası' 'Error' }
})
$btnSave.Add_Click({
    try { $path = Save-UiProfile; Notice ('Profil kaydedildi:' + [Environment]::NewLine + $path) }
    catch { Notice ([string]$_.Exception.Message) 'Kaydedilemedi' 'Error' }
})
$btnDelete.Add_Click({
    try {
        $p = Selected-Profile
        $job = Get-AgfoTaskName $p
        if (-not (Confirm ('Profil ve varsa zamanlanmış görevi kaldırmak istiyor musunuz?' + [Environment]::NewLine + $p.profileName) 'Profil sil')) { return }
        $task = Get-ScheduledTask -TaskName $job -ErrorAction SilentlyContinue
        if ($task) { Unregister-ScheduledTask -TaskName $job -Confirm:$false }
        [System.IO.File]::Delete((Selected-ProfilePath))
        Refresh-ProfileList
    } catch { Notice ([string]$_.Exception.Message) 'Profil silinemedi' 'Error' }
})
$btnImport.Add_Click({
    try {
        $n = Import-AgfoV1Profiles
        Refresh-ProfileList
        Notice ([string]$n + ' adet eski profil eklendi. Aktarılan profiller artımlı moda alındı. Eski v1 gece görevleri varsa ayrıca kaldırın.')
    } catch { Notice ([string]$_.Exception.Message) 'İçe aktarma hatası' 'Error' }
})
$btnTest.Add_Click({
    try {
        $p = Get-UiProfile
        $paths = Validate-AgfoPaths $p $true $false
        Notice ('Kaynak erişilebilir:' + [Environment]::NewLine + $paths.Source + [Environment]::NewLine +
            'Hedef paylaşım kökü erişilebilir:' + [Environment]::NewLine + (Get-AgfoPathRoot $paths.Target) +
            [Environment]::NewLine + 'Not: Bu test yazma izni denemesi yapmaz.')
    } catch { Notice ([string]$_.Exception.Message) 'Bağlantı hatası' 'Warning' }
})
$btnPreview.Add_Click({
    try { Start-UiJob $true }
    catch { Notice ([string]$_.Exception.Message) 'Önizleme başlatılamadı' 'Error' }
})
$btnRun.Add_Click({
    try { Start-UiJob $false }
    catch { Notice ([string]$_.Exception.Message) 'İşlem başlatılamadı' 'Error' }
})
$btnStop.Add_Click({
    if ($script:LiveProcess -and -not $script:LiveProcess.HasExited) {
        if (Confirm 'Çalışan aktarımı durdurmak istiyor musunuz? Yarım kalanlar sonraki çalıştırmada denenir.' 'Aktarımı durdur') {
            [System.IO.File]::WriteAllText($script:LiveCancel, 'stop')
            $lblState.Text = 'Durum: Durdurma isteği gönderildi...'
        }
    }
})
$btnOpenLast.Add_Click({
    $log = if ($script:LiveLog -and [System.IO.File]::Exists($script:LiveLog)) { $script:LiveLog } else { $script:LastLog }
    if ($log) { Open-LocalFile $log } else { Notice 'Henüz log yok.' }
})
$btnSchedule.Add_Click({
    try { Register-AgfoNightTask; Check-AgfoTask }
    catch { Notice ([string]$_.Exception.Message) 'Görev kurulamadı' 'Error' }
})
$btnUnschedule.Add_Click({
    try {
        $p = Selected-Profile
        $name = Get-AgfoTaskName $p
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if (-not $task) { Notice 'Görev yok.'; return }
        if (Confirm ('Görevi kaldır: ' + $name)) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Check-AgfoTask
        }
    } catch { Notice ([string]$_.Exception.Message) 'Görev kaldırılamadı' 'Error' }
})
$btnScheduleStatus.Add_Click({ try { Check-AgfoTask } catch { Notice ([string]$_.Exception.Message) 'Görev sorgulanamadı' 'Error' } })
$btnVersions.Add_Click({ try { Refresh-VersionList } catch { Notice ([string]$_.Exception.Message) 'Arşiv okunamadı' 'Error' } })
$listVersions.Add_SelectedIndexChanged({ Refresh-RestoreSuggestion })
$btnOpenVersions.Add_Click({
    try {
        $p = Selected-Profile
        $folder = Get-AgfoArchiveRoot $p
        if (-not (Test-Path -LiteralPath $folder -PathType Container)) { Notice 'Henüz sürüm arşivi bulunmuyor.'; return }
        Start-Process -FilePath 'explorer.exe' -ArgumentList (Quote-AgfoArg $folder)
    } catch { Notice ([string]$_.Exception.Message) 'Arşiv açılamadı' 'Error' }
})
$btnRestorePreview.Add_Click({
    try {
        $item = $listVersions.SelectedItem
        if (-not $item) { throw 'Önce geri yüklenecek sürümü seçin.' }
        Start-UiJob $true ([string]$item.Path) ($txtRestore.Text.Trim())
    } catch { Notice ([string]$_.Exception.Message) 'Geri yükleme önizleme hatası' 'Error' }
})
$btnRestore.Add_Click({
    try {
        $item = $listVersions.SelectedItem
        if (-not $item) { throw 'Önce geri yüklenecek sürümü seçin.' }
        if (Confirm ('Eski dosyalar şu YENİ klasöre kopyalanacak:' + [Environment]::NewLine + $txtRestore.Text +
            [Environment]::NewLine + 'Canlı dosyalara dokunulmayacak. Devam edilsin mi?' ) 'Geri yüklemeyi onayla') {
            Start-UiJob $false ([string]$item.Path) ($txtRestore.Text.Trim())
        }
    } catch { Notice ([string]$_.Exception.Message) 'Geri yükleme hatası' 'Error' }
})
$btnLogRefresh.Add_Click({ Refresh-LogList })
$btnLogOpen.Add_Click({
    $item = $listLogs.SelectedItem
    if ($item) { Open-LocalFile ([string]$item.Path) } else { Notice 'Listeden bir kayıt seçin.' }
})
$listLogs.Add_DoubleClick({
    $item = $listLogs.SelectedItem
    if ($item) { Open-LocalFile ([string]$item.Path) }
})
$btnLogFolder.Add_Click({ Start-Process -FilePath 'explorer.exe' -ArgumentList (Quote-AgfoArg $script:AgfoLogs) })
$btnEngineCheck.Add_Click({ Engine-Ready })
$btnInstall.Add_Click({
    try {
        if (Find-AgfoExe 'rclone.exe') { Notice 'rclone zaten kurulu.'; return }
        if ($script:InstallProcess -and -not $script:InstallProcess.HasExited) { Notice 'Kurulum devam ediyor.'; return }
        $winget = Find-AgfoExe 'winget.exe'
        if (-not $winget) { throw 'winget bulunamadı. Windows App Installer yükleyin veya Robocopy kullanın.' }
        if (-not (Confirm 'winget üzerinden rclone kurulacaktır. İnternet erişimi gerekir. Devam?' 'rclone kurulumu')) { return }
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $winget
        $psi.Arguments = 'install --id Rclone.Rclone --exact --source winget --accept-source-agreements --accept-package-agreements --silent'
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $script:InstallProcess = New-Object System.Diagnostics.Process
        $script:InstallProcess.StartInfo = $psi
        if (-not $script:InstallProcess.Start()) { throw 'winget başlatılamadı.' }
        $btnInstall.Enabled = $false
        $lblEngine.Text = 'winget kurulumu çalışıyor...'
    } catch { Notice ([string]$_.Exception.Message) 'Kurulum hatası' 'Error' }
})


function Selected-DriveRow {
    if ($listDrives.SelectedItems.Count -eq 0) { throw 'Listeden bir esleme secin.' }
    return $listDrives.SelectedItems[0].Tag
}
function Start-AgfoDriveAction([string]$Action) {
    if ($script:DriveProcess -and -not $script:DriveProcess.HasExited) { throw 'Diger surucu islemi devam ediyor.' }
    $exe = Join-Path $PSScriptRoot 'AGFO-BackupSync.exe'
    if (-not [System.IO.File]::Exists($exe)) { throw 'Windows surucu yardimcisi kurulu degil.' }
    $folder = Join-Path $env:LOCALAPPDATA 'AGFO-BackupSync\discovery'
    [void][System.IO.Directory]::CreateDirectory($folder)
    $out = Join-Path $folder (([guid]::NewGuid().ToString('N')) + '.drive.json')
    $params = @('--output', $out)
    switch ($Action) {
        'list' { $params += '--drive-list' }
        'map' {
            if ($null -eq $cmbDriveLetter.SelectedItem) { throw 'Bos surucu harfi bulunamadi.' }
            $params += @('--drive-map', $txtDrivePath.Text.Trim(), '--letter', [string]$cmbDriveLetter.SelectedItem)
            if ($chkDrivePersist.Checked) { $params += '--persistent' }
        }
        'unmap' {
            $selected = Selected-DriveRow
            $params += @('--drive-unmap', [string]$selected.letter)
        }
        default { throw 'Taninmayan surucu islemi.' }
    }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.Arguments = Join-AgfoArgs $params
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    Set-AgfoHelperEnvironment $psi
    $script:DriveProcess = New-Object System.Diagnostics.Process
    $script:DriveProcess.StartInfo = $psi
    if (-not $script:DriveProcess.Start()) { throw 'Surucu yardimcisi baslatilamadi.' }
    $script:DriveAction = $Action
    $script:DriveFile = $out
    $script:DriveStarted = Get-Date
    $lblDriveStatus.Text = 'Surucu islemi devam ediyor: ' + $Action
    $btnDriveMap.Enabled = $false
    $btnDriveUnmap.Enabled = $false
    $btnDriveRefresh.Enabled = $false
}
function Finish-AgfoDriveAction {
    if (-not $script:DriveProcess -or -not $script:DriveProcess.HasExited) { return }
    $code = $script:DriveProcess.ExitCode
    $script:DriveProcess.Dispose()
    $script:DriveProcess = $null
    $btnDriveMap.Enabled = $true
    $btnDriveUnmap.Enabled = $true
    $btnDriveRefresh.Enabled = $true
    $action = $script:DriveAction
    $completedFile = $script:DriveFile
    try {
        if (-not [System.IO.File]::Exists($completedFile)) { throw 'Surucu islemi raporu bulunamadi. Kod: ' + $code }
        $result = Read-AgfoJson $completedFile
        if (-not [bool]$result.ok) { throw ([string]$result.message) }
        $lblDriveStatus.Text = [string]$result.message
        if ($action -eq 'list') {
            $listDrives.Items.Clear()
            foreach ($mapping in @($result.mappings)) {
                if ($null -eq $mapping) { continue }
                $row = New-Object System.Windows.Forms.ListViewItem ([string]$mapping.letter)
                [void]$row.SubItems.Add([string]$mapping.kind)
                [void]$row.SubItems.Add([string]$mapping.target)
                [void]$row.SubItems.Add([string]$mapping.state)
                $row.Tag = $mapping
                [void]$listDrives.Items.Add($row)
            }
            $previous = [string]$cmbDriveLetter.SelectedItem
            $cmbDriveLetter.Items.Clear()
            foreach ($available in @($result.free_letters)) {
                if ($available) { [void]$cmbDriveLetter.Items.Add([string]$available) }
            }
            if ($cmbDriveLetter.Items.Count -gt 0) {
                $i = $cmbDriveLetter.Items.IndexOf($previous)
                if ($i -lt 0) { $i = $cmbDriveLetter.Items.IndexOf('Z:') }
                if ($i -lt 0) { $i = $cmbDriveLetter.Items.Count - 1 }
                $cmbDriveLetter.SelectedIndex = $i
            }
        } else {
            Start-AgfoDriveAction 'list'
            try { Start-AgfoDiscovery 'known' } catch { }
        }
    } catch { $lblDriveStatus.Text = 'Surucu islemi basarisiz: ' + [string]$_.Exception.Message }
    finally { try { [System.IO.File]::Delete($completedFile) } catch { } }
}
$txtDrivePath.Add_TextChanged({
    $isRemote = $txtDrivePath.Text.Trim().StartsWith('\\')
    if (-not $isRemote) { $chkDrivePersist.Checked = $false }
    $chkDrivePersist.Enabled = $isRemote
})
$btnDriveMap.Add_Click({
    try { Start-AgfoDriveAction 'map' }
    catch { Notice ([string]$_.Exception.Message) 'Surucu baglanamadi' 'Warning' }
})
$btnDriveUnmap.Add_Click({
    try {
        if ($script:LiveProcess -and -not $script:LiveProcess.HasExited) { throw 'Aktarim surerken surucu baglantisini kaldirmayin.' }
        $item = Selected-DriveRow
        if (-not (Confirm ("Esleme kaldirilacak: " + [string]$item.letter + ' -> ' + [string]$item.target +
            [Environment]::NewLine + 'Bu islem NAS dosyalarini silmez. Devam?') 'Surucu baglantisini kaldir')) { return }
        Start-AgfoDriveAction 'unmap'
    } catch { Notice ([string]$_.Exception.Message) 'Surucu kaldirma' 'Warning' }
})
$btnDriveRefresh.Add_Click({ try { Start-AgfoDriveAction 'list' } catch { Notice ([string]$_.Exception.Message) 'Surucu listesi' 'Warning' } })
$btnDriveBrowse.Add_Click({
    try {
        $item = Selected-DriveRow
        Start-Process -FilePath 'explorer.exe' -ArgumentList (Quote-AgfoArg ([string]$item.letter + '\'))
    } catch { Notice ([string]$_.Exception.Message) 'Surucuyu ac' 'Warning' }
})
$btnDriveSource.Add_Click({
    try {
        $item = Selected-DriveRow
        $txtSource.Text = [string]$item.target
        $tabs.SelectedTab = $tabBackup
    } catch { Notice ([string]$_.Exception.Message) 'Kaynak secimi' 'Warning' }
})
$btnDriveTarget.Add_Click({
    try {
        $item = Selected-DriveRow
        $txtTarget.Text = [string]$item.target
        $tabs.SelectedTab = $tabBackup
        if ($cmbMode.SelectedIndex -eq 2) { Notice 'Surumlu esitleme icin disk veya paylasim kokunu degil, ayri bir alt klasoru kullanin.' }
    } catch { Notice ([string]$_.Exception.Message) 'Hedef secimi' 'Warning' }
})
$btnNetworkToDrive.Add_Click({
    try {
        $txtDrivePath.Text = Get-SelectedNetworkPath
        $chkDrivePersist.Checked = $true
        $tabs.SelectedTab = $tabDrives
    } catch { Notice ([string]$_.Exception.Message) 'Surucu esleme' 'Warning' }
})

function Get-SelectedNetworkItem {
    if ($listNetwork.SelectedItems.Count -eq 0) { throw 'Once ag listesinden bir satir secin.' }
    return $listNetwork.SelectedItems[0]
}
function Get-SelectedNetworkPath([bool]$AllowHost = $false) {
    $item = Get-SelectedNetworkItem
    if (-not $AllowHost -and -not [bool]$item.Tag.selectable) {
        throw 'Bu bir sunucu satiri. Dosya Gezgini ile paylasim secin veya UNC yolu girin.'
    }
    return [string]$item.Tag.path
}
function Start-AgfoDiscovery([string]$Mode, [string]$NetworkPath = '') {
    if ($script:DiscoveryProcess -and -not $script:DiscoveryProcess.HasExited) {
        throw 'Baska ag kesif/test islemi suruyor. Bitmesini bekleyin.'
    }
    $exe = Join-Path $PSScriptRoot 'AGFO-BackupSync.exe'
    if (-not [System.IO.File]::Exists($exe)) {
        throw 'Ag kesif yardimcisi yok. v2.2 kurulum paketindeki AGFO-BackupSync.exe gereklidir.'
    }
    $dir = Join-Path $env:LOCALAPPDATA 'AGFO-BackupSync\discovery'
    [void][System.IO.Directory]::CreateDirectory($dir)
    $out = Join-Path $dir (([guid]::NewGuid().ToString('N')) + '.json')
    $params = if ($Mode -eq 'probe') { @('--probe', $NetworkPath, '--output', $out) } else { @('--discover', $Mode, '--output', $out) }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.Arguments = Join-AgfoArgs $params
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    Set-AgfoHelperEnvironment $psi
    $script:DiscoveryProcess = New-Object System.Diagnostics.Process
    $script:DiscoveryProcess.StartInfo = $psi
    if (-not $script:DiscoveryProcess.Start()) { throw 'Kesif yardimcisi baslatilamadi.' }
    $script:DiscoveryFile = $out
    $script:DiscoveryMode = $Mode
    $script:DiscoveryStarted = Get-Date
    $lblDiscovery.Text = switch ($Mode) {
        'known' { 'Bagli ag suruculeri ve profiller okunuyor...' }
        'scan' { 'Yerel IPv4 aginda SMB/445 taraniyor. Ag yogunlugune gore biraz surebilir...' }
        default { 'Secili klasorun okunabilirligi test ediliyor...' }
    }
    $btnDiscoveryKnown.Enabled = $false
    $btnDiscoveryScan.Enabled = $false
    $btnDiscoveryTest.Enabled = $false
}
function Finish-AgfoDiscovery {
    $proc = $script:DiscoveryProcess
    if (-not $proc) { return }
    $code = $proc.ExitCode
    $proc.Dispose()
    $script:DiscoveryProcess = $null
    $btnDiscoveryKnown.Enabled = $true
    $btnDiscoveryScan.Enabled = $true
    $btnDiscoveryTest.Enabled = $true
    try {
        if (-not [System.IO.File]::Exists($script:DiscoveryFile)) { throw 'Kesif sonucu olusturulamadi. Hata kodu: ' + $code }
        $data = Read-AgfoJson $script:DiscoveryFile
        if ($script:DiscoveryMode -eq 'probe') {
            if ($script:ProbeListItem) {
                $script:ProbeListItem.SubItems[3].Text = if ([bool]$data.ok) { 'Okunabilir' } else { 'Erisim yok' }
            }
            $lblDiscovery.Text = [string]$data.message
        } else {
            $listNetwork.Items.Clear()
            foreach ($entry in @($data.items)) {
                if ($null -eq $entry) { continue }
                $row = New-Object System.Windows.Forms.ListViewItem ([string]$entry.kind)
                [void]$row.SubItems.Add([string]$entry.name)
                [void]$row.SubItems.Add([string]$entry.path)
                [void]$row.SubItems.Add([string]$entry.state)
                $row.Tag = $entry
                [void]$listNetwork.Items.Add($row)
            }
            $notes = @($data.warnings | Where-Object { $_ })
            $lblDiscovery.Text = 'Bulunan konum: ' + $listNetwork.Items.Count + '.  ' + ($notes -join ' | ')
            if (-not $notes.Count) { $lblDiscovery.Text += ' SMB paylasimlari icin kaynak/hedef secilebilir.' }
        }
    } catch { $lblDiscovery.Text = 'Ag kesif hatasi: ' + [string]$_.Exception.Message }
    finally {
        try { if ([System.IO.File]::Exists($script:DiscoveryFile)) { [System.IO.File]::Delete($script:DiscoveryFile) } } catch { }
    }
}
$btnDiscoveryKnown.Add_Click({ try { Start-AgfoDiscovery 'known' } catch { Notice ([string]$_.Exception.Message) 'Ag kesif sorunu' 'Warning' } })
$btnDiscoveryScan.Add_Click({
    if (-not (Confirm 'Yerel ozel IPv4 aginizda en fazla iki /24 ag blogunda TCP/445 taramasi yapilacak. Parola denenmeyecek, SMB1 acilmayacak. Devam?' 'Yerel SMB kesfi')) { return }
    try { Start-AgfoDiscovery 'scan' } catch { Notice ([string]$_.Exception.Message) 'SMB tarama sorunu' 'Warning' }
})
$btnDiscoveryTest.Add_Click({
    try {
        $script:ProbeListItem = Get-SelectedNetworkItem
        $path = Get-SelectedNetworkPath
        Start-AgfoDiscovery 'probe' $path
    } catch { Notice ([string]$_.Exception.Message) 'Baglanti testi' 'Warning' }
})
$btnNetworkSource.Add_Click({
    try {
        $txtSource.Text = Get-SelectedNetworkPath
        $tabs.SelectedTab = $tabBackup
    } catch { Notice ([string]$_.Exception.Message) 'Kaynak secimi' 'Warning' }
})
$btnNetworkTarget.Add_Click({
    try {
        $txtTarget.Text = Get-SelectedNetworkPath
        $tabs.SelectedTab = $tabBackup
        if ($cmbMode.SelectedIndex -eq 2) { Notice 'Surumlu esitleme icin paylasim kokunu degil, altinda ayri bir klasor secin.' }
    } catch { Notice ([string]$_.Exception.Message) 'Hedef secimi' 'Warning' }
})
$btnNetworkSubfolder.Add_Click({
    try {
        $row = Get-SelectedNetworkItem
        $initial = Get-SelectedNetworkPath
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        try {
            $dlg.Description = 'Ag paylasimi icinde kaynak/hedef alt klasorunu secin.'
            $dlg.SelectedPath = $initial
            if ($dlg.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) {
                if (-not $dlg.SelectedPath) { throw 'Alt klasor secilmedi.' }
                $row.SubItems[2].Text = [string]$dlg.SelectedPath
                $row.Tag.path = [string]$dlg.SelectedPath
                $row.SubItems[3].Text = 'Secildi; erisimi test edin'
            }
        } finally { $dlg.Dispose() }
    } catch { Notice ([string]$_.Exception.Message) 'Alt klasor' 'Warning' }
})
$btnDiscoveryBrowse.Add_Click({
    try { Start-Process -FilePath 'explorer.exe' -ArgumentList (Quote-AgfoArg (Get-SelectedNetworkPath $true)) }
    catch { Notice ([string]$_.Exception.Message) 'Dosya Gezgini' 'Warning' }
})
$listNetwork.Add_DoubleClick({
    try { Start-Process -FilePath 'explorer.exe' -ArgumentList (Quote-AgfoArg (Get-SelectedNetworkPath $true)) }
    catch { Notice ([string]$_.Exception.Message) 'Dosya Gezgini' 'Warning' }
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 1400
$timer.Add_Tick({
    try {
        if ($script:InstallProcess -and $script:InstallProcess.HasExited) {
            $code = $script:InstallProcess.ExitCode
            $script:InstallProcess.Dispose()
            $script:InstallProcess = $null
            $btnInstall.Enabled = $true
            Engine-Ready
            if ($code -eq 0) { Notice 'rclone kurulumu tamamlandı. Gerekirse GUI uygulamasını yeniden başlatın.' }
            else { Notice ('winget kurulum hata kodu: ' + $code) 'rclone kurulumu' 'Warning' }
        }
        if ($script:DiscoveryProcess) {
            if ($script:DiscoveryProcess.HasExited) {
                Finish-AgfoDiscovery
            } elseif (((Get-Date) - $script:DiscoveryStarted).TotalSeconds -gt 90) {
                try { $script:DiscoveryProcess.Kill() } catch { }
                $lblDiscovery.Text = 'Ag kesfi 90 saniye asimi nedeniyle durduruldu. Baglanti/firewall ayarlarini denetleyin.'
                Finish-AgfoDiscovery
            }
        }
        if ($script:DriveProcess) {
            if ($script:DriveProcess.HasExited) {
                Finish-AgfoDriveAction
            } elseif (((Get-Date) - $script:DriveStarted).TotalSeconds -gt 50) {
                try { $script:DriveProcess.Kill() } catch { }
                $lblDriveStatus.Text = 'Surucu islemi zaman asimina ugradi. NAS/Windows baglantisini kontrol edin.'
                if ($script:DriveProcess.HasExited) { Finish-AgfoDriveAction }
            }
        }

        if ($script:LiveProcess) {
            Tail-UiLog
            if ($script:LiveProcess.HasExited) {
                Tail-UiLog
                $code = $script:LiveProcess.ExitCode
                $script:LiveProcess.Dispose()
                $script:LiveProcess = $null
                Set-RunState $false
                if ([System.IO.File]::Exists($script:LiveStatus)) {
                    $result = Read-AgfoJson $script:LiveStatus
                    $lblState.Text = ('Durum: ' + [string]$result.state + ' | ' + [string]$result.message)
                    $script:LastLog = [string]$result.log
                } else {
                    $lblState.Text = ('İşlem durdu (kod ' + $code + '). Sonuç dosyası bulunamadı; tanılama çalıştırın.')
                }
                Refresh-LogList
                try { Refresh-VersionList } catch { }
            }
        }
    } catch { $lblState.Text = 'İzleme sorunu: ' + [string]$_.Exception.Message }
})
$script:AgfoSmoke = ($env:AGFO_GUI_SMOKE -eq '1')
$form.Add_Shown({
    if ($script:AgfoSmoke) { return }
    try {
        $old = Import-AgfoV1Profiles
        $profiles = @(Get-AgfoProfiles)
        if ($profiles.Count -eq 0) {
            $p = New-AgfoProfile
            $null = Save-AgfoProfile $p
        }
        Refresh-ProfileList
        Refresh-LogList
        Engine-Ready
        $timer.Start()
        try { Start-AgfoDiscovery 'known' } catch { $lblDiscovery.Text = [string]$_.Exception.Message }
        try { Start-AgfoDriveAction 'list' } catch { $lblDriveStatus.Text = [string]$_.Exception.Message }

        if ($old -gt 0) { Notice ($old.ToString() + ' adet v1 profili içe aktarıldı. Artımlı moda alındı. v1 zamanlanmış görevleri kontrol edin.') }
    } catch { Notice ([string]$_.Exception.Message) 'Açılış sorunu' 'Error' }
})
$form.Add_FormClosing({
    param($sender, $eventArgs)
    if ($script:LiveProcess -and -not $script:LiveProcess.HasExited) {
        if (-not (Confirm 'Pencere kapatılacak ancak işlem arka planda devam edecek. Emin misiniz?' 'İşlem devam ediyor')) {
            $eventArgs.Cancel = $true
            return
        }
    }
    $timer.Stop()
    if ($script:DriveProcess -and -not $script:DriveProcess.HasExited) {
        try { $script:DriveProcess.Kill() } catch { }
    }
    if ($script:DiscoveryProcess -and -not $script:DiscoveryProcess.HasExited) {
        try { $script:DiscoveryProcess.Kill() } catch { }
    }
})
if ($env:AGFO_GUI_SMOKE -eq '1') {
    # CI smoke test: builds every control, renders each tab to one PNG sheet, exits without showing a window.
    try {
        # Sample rows so the rendered sheet shows real list styling (smoke mode only, nothing is saved).
        [void]$listProfiles.Items.Add([pscustomobject]@{ Name = 'Synology-UGREEN'; Path = '' })
        [void]$listProfiles.Items.Add([pscustomobject]@{ Name = 'Belgeler -> NAS'; Path = '' })
        foreach ($row in @(@('Ag surucusu', 'Z:', '\\NAS\Yedek', 'Bagli'), @('SMB sunucusu', 'NAS', '\\192.168.1.20', 'Port 445 acik'))) {
            $item = New-Object System.Windows.Forms.ListViewItem ([string]$row[0])
            foreach ($cell in $row[1..3]) { [void]$item.SubItems.Add([string]$cell) }
            [void]$listNetwork.Items.Add($item)
        }
        foreach ($row in @(@('Z:', 'NET USE', '\\NAS\Yedek', 'Bagli'), @('S:', 'SUBST', 'C:\Belgeler\Arsiv', 'Yerel'))) {
            $item = New-Object System.Windows.Forms.ListViewItem ([string]$row[0])
            foreach ($cell in $row[1..3]) { [void]$item.SubItems.Add([string]$cell) }
            [void]$listDrives.Items.Add($item)
        }
        $txtLiveLog.Text = '[02:00:01] Yedekleme basladi' + [Environment]::NewLine + '[02:00:04] 1.284 dosya kontrol edildi'
        # Child controls only paint when the form is shown: show it off-screen, without the Shown handler.
        $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
        $form.Location = [System.Drawing.Point]::new(-32000, -32000)
        $form.ShowInTaskbar = $false
        $form.Show()
        [System.Windows.Forms.Application]::DoEvents()
        $out = if ($env:AGFO_GUI_SMOKE_OUT) { $env:AGFO_GUI_SMOKE_OUT } else { Join-Path $env:TEMP 'agfo-gui-smoke.png' }
        $w = $form.Width
        $h = $form.Height
        $sheet = [System.Drawing.Bitmap]::new($w * 2, $h * 3)
        $g = [System.Drawing.Graphics]::FromImage($sheet)
        for ($i = 0; $i -lt $tabs.TabPages.Count; $i++) {
            $tabs.SelectedIndex = $i
            [System.Windows.Forms.Application]::DoEvents()
            $bmp = [System.Drawing.Bitmap]::new($w, $h)
            $form.DrawToBitmap($bmp, [System.Drawing.Rectangle]::new(0, 0, $w, $h))
            $g.DrawImage($bmp, [int](($i % 2) * $w), [int]([Math]::Floor($i / 2) * $h))
            $bmp.Dispose()
        }
        $g.Dispose()
        $sheet.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
        $sheet.Dispose()
        Write-Output ('AGFO GUI SMOKE OK: ' + $tabs.GetType().FullName + ' -> ' + $out)
        $form.Hide()
    } finally { $timer.Dispose(); $form.Dispose() }
    return
}
try { [void]$form.ShowDialog() }
finally { $timer.Dispose(); $form.Dispose() }
