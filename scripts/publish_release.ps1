param(
    [Parameter(Mandatory=$true)][string]$Commit,
    [string]$Tag='v2.1.0',
    [long]$ResumeDraftId=0
)
$ErrorActionPreference='Stop'
$ReleaseRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ReleaseRoot
if ($Commit -notmatch '^[a-f0-9]{40}$' -or $Tag -ne 'v2.1.0') { throw 'Unexpected release identity' }
if ((git rev-parse HEAD) -ne $Commit) { throw 'Release commit is not local HEAD' }
$ReleaseRemote=git ls-remote origin refs/heads/main
if ($LASTEXITCODE -ne 0 -or $ReleaseRemote -notmatch "^$Commit\s") { throw 'Commit is not pushed to main' }
$ReleaseAssets=@('dist/M2P-Studio.exe','dist/Music2Picture-2.1.0-source.zip','dist/SHA256SUMS.txt')
foreach ($Asset in $ReleaseAssets) { if (-not (Test-Path -LiteralPath $Asset -PathType Leaf)) { throw "Missing asset: $Asset" } }
$CredentialLines="protocol=https`nhost=github.com`n`n" | git credential fill
$Credentials=@{}
try {
    foreach ($Line in $CredentialLines) { if ($Line -match '^([^=]+)=(.*)$') { $Credentials[$matches[1]]=$matches[2] } }
    if (-not $Credentials.password) { throw 'GitHub authentication unavailable' }
    $Headers=@{ Authorization=('Bearer '+$Credentials.password); Accept='application/vnd.github+json';
                'User-Agent'='Music2Picture-release'; 'X-GitHub-Api-Version'='2022-11-28' }
    $Api='https://api.github.com/repos/dumuzeyn/Music2Picture'
    $Repository=Invoke-RestMethod -Uri $Api -Headers $Headers
    if ($Repository.full_name -ne 'dumuzeyn/Music2Picture' -or -not $Repository.permissions.push) { throw 'Wrong repository or no publishing permission' }
    $Existing=Invoke-RestMethod -Uri "$Api/releases?per_page=100" -Headers $Headers
    $Matching=$Existing | Where-Object tag_name -eq $Tag
    if ($Matching -and (-not $ResumeDraftId -or $Matching.id -ne $ResumeDraftId -or -not $Matching.draft)) {
        throw 'Release already exists; it will not be overwritten'
    }
    $Body=Get-Content -LiteralPath 'docs/RELEASE-2.1.0.md' -Raw -Encoding UTF8
    $Payload=@{tag_name=$Tag; target_commitish=$Commit; name='Music2Picture 2.1.0 — M2Pv1 + M2Pv2 Studio';
               body=$Body; draft=$true; prerelease=$false} | ConvertTo-Json
    if ($ResumeDraftId) {
        if (-not $Matching) { throw 'Draft to resume was not verified' }
        $Draft=Invoke-RestMethod -Method Patch -Uri "$Api/releases/$ResumeDraftId" -Headers $Headers `
            -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($Payload))
    } else {
        $Draft=Invoke-RestMethod -Method Post -Uri "$Api/releases" -Headers $Headers `
            -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($Payload))
    }
    Write-Output "Private release draft: $($Draft.id)"
    $Prior=Invoke-RestMethod -Uri "$Api/releases/$($Draft.id)/assets" -Headers $Headers
    foreach ($Asset in $ReleaseAssets) {
        $File=Get-Item -LiteralPath $Asset
        $Hash=(Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $Already=$Prior | Where-Object name -eq $File.Name
        if ($Already) {
            if ($Already.state -ne 'uploaded' -or $Already.size -ne $File.Length -or
                $Already.digest -ne ('sha256:'+$Hash)) { throw 'Draft asset does not match local file' }
            continue
        }
        $Upload=($Draft.upload_url -replace '\{.*\}$','')+'?name='+[Uri]::EscapeDataString($File.Name)
        Write-Output "Uploading $($File.Name) ($([Math]::Round($File.Length/1MB,2)) MB)"
        $Uploaded=Invoke-RestMethod -Method Post -Uri $Upload -Headers $Headers -ContentType 'application/octet-stream' `
            -InFile $File.FullName -TimeoutSec 1800
        if ($Uploaded.state -ne 'uploaded' -or $Uploaded.size -ne $File.Length -or
            ($Uploaded.digest -and $Uploaded.digest -ne ('sha256:'+$Hash))) {
            throw 'Upload verification failed; release remains private'
        }
    }
    $UploadedAssets=Invoke-RestMethod -Uri "$Api/releases/$($Draft.id)/assets" -Headers $Headers
    if (@($UploadedAssets).Count -ne $ReleaseAssets.Count) { throw 'Incomplete assets; draft remains private' }
    $Published=Invoke-RestMethod -Method Patch -Uri "$Api/releases/$($Draft.id)" -Headers $Headers `
        -ContentType 'application/json' -Body '{"draft":false,"make_latest":"true"}'
    if ($Published.draft -or $Published.tag_name -ne $Tag) { throw 'Release publication could not be confirmed' }
    Write-Output "Published $($Published.html_url)"
    $Published.assets | Select-Object name,size,digest,browser_download_url
} finally {
    $Credentials.Clear()
    if ($Headers) { $Headers.Clear() }
    $CredentialLines=$null
}
