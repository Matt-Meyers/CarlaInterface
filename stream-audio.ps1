param(
    [Parameter(Mandatory = $true)]
    [string]$Target
)

$ErrorActionPreference = "Stop"

$hostPart = if ($Target -match '@') { ($Target -split '@', 2)[1] } else { $Target }
if ($hostPart -notmatch '^(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}$') {
    throw "Target must include an IPv4 address (got '$Target')."
}
$subnetPrefix = $Matches[1]

if (-not ("CarlaListenCtrl" -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.Threading;
public static class CarlaListenCtrl {
    public static volatile bool Arm;
    public static volatile bool Cancelled;
    public static volatile int SshPid;
    public static string Target = "";
    static readonly object Gate = new object();
    static CarlaListenCtrl() {
        Console.CancelKeyPress += delegate (object sender, ConsoleCancelEventArgs e) {
            if (!Arm) return;
            Arm = false;
            Cancelled = true;
            e.Cancel = true;
            Stop();
        };
    }
    public static void Stop() {
        lock (Gate) {
            try {
                if (SshPid > 0) {
                    Process ssh = Process.GetProcessById(SshPid);
                    if (!ssh.HasExited && string.Equals(ssh.ProcessName, "ssh", StringComparison.OrdinalIgnoreCase))
                        ssh.Kill();
                }
            } catch (Exception) {}
            if (string.IsNullOrEmpty(Target)) return;
            try {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "ssh.exe";
                psi.Arguments = "-o BatchMode=yes -o ConnectTimeout=5 " + Target
                    + " \"pkill -f '[j]ack -i grab' || true\"";
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                Process killer = Process.Start(psi);
                if (killer != null) killer.WaitForExit(15000);
            } catch (Exception) {}
        }
    }
}
'@
}

# Touch the type so the Ctrl+C hook is installed before anything is armed.
[CarlaListenCtrl]::Arm = $false

$localIp = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -like "$subnetPrefix.*" } |
    Select-Object -ExpandProperty IPAddress -First 1
if (-not $localIp) {
    throw "No $subnetPrefix.x address on this PC."
}

# Own SSH call: the ffmpeg command contains this same text, so pkill in that
# shell would match itself and exit before ffmpeg starts.
& ssh.exe -o BatchMode=yes -o ConnectTimeout=8 $Target "pkill -f '[j]ack -i grab' || true"

$remote = @"
export XDG_RUNTIME_DIR=/run/user/`$(id -u); exec ffmpeg -nostdin -fflags nobuffer -flags low_delay -f jack -i grab -ac 2 -c:a libopus -application lowdelay -frame_duration 20 -b:a 128k -flush_packets 1 -muxdelay 0 -muxpreload 0 -f mpegts 'udp://${localIp}:1234?pkt_size=1316'
"@.Trim()

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "ssh.exe"
$psi.Arguments = "-o BatchMode=yes -o ConnectTimeout=8 $Target `"$remote`""
$psi.UseShellExecute = $false
$psi.RedirectStandardError = $true
$psi.RedirectStandardOutput = $true
$psi.CreateNoWindow = $true

$ssh = New-Object System.Diagnostics.Process
$ssh.StartInfo = $psi
[void]$ssh.Start()
$outTask = $ssh.StandardOutput.ReadToEndAsync()
$errTask = $ssh.StandardError.ReadToEndAsync()

[CarlaListenCtrl]::Target = $Target
[CarlaListenCtrl]::SshPid = $ssh.Id
[CarlaListenCtrl]::Cancelled = $false
[CarlaListenCtrl]::Arm = $true

try {
    Start-Sleep -Seconds 1
    if ([CarlaListenCtrl]::Cancelled) { return }
    if ($ssh.HasExited) {
        throw "ssh/ffmpeg exited ($($ssh.ExitCode)).`n$($outTask.Result)`n$($errTask.Result)"
    }
    ffplay -f mpegts -fflags nobuffer -flags low_delay udp://0.0.0.0:1234
}
finally {
    # Closing the local ssh client does not stop remote ffmpeg (it ignores the
    # broken pipe). pkill has to match "-f jack -i grab".
    [CarlaListenCtrl]::Arm = $false
    [CarlaListenCtrl]::Stop()
}
