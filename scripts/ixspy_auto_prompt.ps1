Set-Location "D:\ProductSourcingSystem"
$env:EMBEDDING_REPO_DIR = "D:\518"
$cat = Read-Host "Enter category name (Chinese OK, e.g. auto parts category)"
if ([string]::IsNullOrWhiteSpace($cat)) {
    Write-Host "No category entered. Exiting."
    Read-Host "Press Enter to close"
    exit 1
}
python -X utf8 -m sourcing.cli ixspy-auto --category "$cat"
Read-Host "Done. Press Enter to close"
