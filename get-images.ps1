# Copies the images this site needs out of your WordPress uploads folder.
# Pure PowerShell - nothing to install. Windows has this built in.
param([string]$Source)

$ErrorActionPreference = 'Stop'
# filenames contain en-dashes; force UTF-8 everywhere or they mangle to "a EUR"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
# In the repo layout the pages live in a 'site' subfolder; images belong in there,
# not next to this script. Step into it automatically if it exists.
if (Test-Path (Join-Path $here 'site')) { $here = Join-Path $here 'site' }
$manifest = Join-Path $here 'images-needed.txt'

if (-not (Test-Path $manifest)) {
    Write-Host "ERROR: images-needed.txt is not next to this script." -ForegroundColor Red
    Write-Host "Make sure you are running this from inside the 'site' folder."
    return
}
if (-not $Source -or -not (Test-Path $Source)) {
    Write-Host "ERROR: cannot find that folder:" -ForegroundColor Red
    Write-Host "  $Source"
    return
}

# If they pointed at wp-content, or at the extracted zip root, step inside for them
$probe = Join-Path $Source 'uploads'
if ((Split-Path $Source -Leaf) -ne 'uploads' -and (Test-Path $probe)) {
    $Source = $probe
    Write-Host "(Using the uploads folder inside: $Source)`n"
}

Write-Host "Source : $Source"
Write-Host "Target : $(Join-Path $here 'wp-content\uploads')`n"

Write-Host "Indexing your image folder. This takes a moment..."
$index = @{}
$all = Get-ChildItem -Path $Source -Recurse -File -ErrorAction SilentlyContinue
foreach ($f in $all) {
    $k = $f.Name.ToLower()
    if (-not $index.ContainsKey($k)) { $index[$k] = @() }
    $index[$k] += $f.FullName
}
Write-Host ("  {0:N0} files found`n" -f $all.Count)

$wanted  = Get-Content $manifest -Encoding UTF8 | Where-Object { $_.Trim() -ne '' }
$copied  = 0
$missing = New-Object System.Collections.ArrayList

foreach ($rel in $wanted) {
    $relpath = $rel -replace '^/wp-content/uploads/', ''
    $relwin  = $relpath -replace '/', '\'
    $dest    = Join-Path $here (Join-Path 'wp-content\uploads' $relwin)

    $found = $null
    $exact = Join-Path $Source $relwin
    if (Test-Path $exact) {
        $found = $exact
    } else {
        $base = [System.IO.Path]::GetFileName($relpath).ToLower()
        if ($index.ContainsKey($base)) {
            $found = ($index[$base] | Sort-Object { (Get-Item $_).Length } -Descending)[0]
        } else {
            # try without the WordPress -000x000 size suffix
            $stripped = [regex]::Replace($base, '-\d+x\d+(\.\w+)$', '$1')
            if ($index.ContainsKey($stripped)) {
                $found = ($index[$stripped] | Sort-Object { (Get-Item $_).Length } -Descending)[0]
            } else {
                # last resort: any file starting with the same stem
                $stem = [System.IO.Path]::GetFileNameWithoutExtension($base)
                $hit = $index.Keys | Where-Object { $_.StartsWith($stem) } | Select-Object -First 1
                if ($hit) { $found = ($index[$hit] | Sort-Object { (Get-Item $_).Length } -Descending)[0] }
            }
        }
    }

    if ($found) {
        $dir = Split-Path $dest -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Copy-Item $found $dest -Force
        $copied++
    } else {
        [void]$missing.Add($rel)
    }
}

Write-Host ""
Write-Host "Copied  : $copied of $($wanted.Count)" -ForegroundColor Green
Write-Host "Missing : $($missing.Count)" -ForegroundColor $(if ($missing.Count) { 'Yellow' } else { 'Green' })

if ($missing.Count) {
    $missing | Set-Content (Join-Path $here 'images-missing.txt') -Encoding UTF8
    Write-Host ""
    Write-Host "Not found (full list is in images-missing.txt):"
    $missing | Select-Object -First 20 | ForEach-Object { Write-Host "   $_" }
    if ($missing.Count -gt 20) { Write-Host "   ... and $($missing.Count - 20) more" }
}

$wc = Join-Path $here 'wp-content'
if (Test-Path $wc) {
    $mb = (Get-ChildItem $wc -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
    Write-Host ""
    Write-Host ("Images folder: {0:N1} MB" -f $mb)
}
Write-Host "Every image is now part of the site. Nothing points at your VPS." -ForegroundColor Green
