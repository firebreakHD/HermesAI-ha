param(
    [Parameter(Mandatory = $true)]
    [string]$HomeAssistantHost,

    [int]$AddonPort = 1456,
    [int]$LocalPort = 1455
)

$ErrorActionPreference = 'Stop'
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $LocalPort)
$listener.Start()
Write-Host "Forwarding localhost:$LocalPort to ${HomeAssistantHost}:$AddonPort. Stop with Ctrl+C."

try {
    while ($true) {
        $localClient = $listener.AcceptTcpClient()
        $remoteClient = [System.Net.Sockets.TcpClient]::new()
        try {
            $remoteClient.Connect($HomeAssistantHost, $AddonPort)
            $localStream = $localClient.GetStream()
            $remoteStream = $remoteClient.GetStream()
            $toAddon = $localStream.CopyToAsync($remoteStream)
            $toBrowser = $remoteStream.CopyToAsync($localStream)
            [System.Threading.Tasks.Task]::WaitAny([System.Threading.Tasks.Task[]]@($toAddon, $toBrowser)) | Out-Null
        }
        catch {
            Write-Warning "Callback forwarding failed: $_"
        }
        finally {
            $localClient.Dispose()
            $remoteClient.Dispose()
        }
    }
}
finally {
    $listener.Stop()
}
