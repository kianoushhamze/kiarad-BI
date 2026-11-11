# Read the actual PostgreSQL container configuration, not a second .env parser.
function Get-PostgresContainerSettings {
    param([Parameter(Mandatory=$true)][string]$ContainerName)
    $raw = & docker inspect --format '{{json .Config.Env}}' $ContainerName
    if ($LASTEXITCODE -ne 0) { throw 'postgres_container_inspection_failed' }
    $values = @{}
    $environment = $raw | ConvertFrom-Json
    foreach ($entry in $environment) {
        $parts = $entry.Split('=', 2)
        if ($parts.Count -eq 2 -and $parts[0] -in @('POSTGRES_USER','POSTGRES_DB')) { $values[$parts[0]] = $parts[1] }
    }
    $user = if ($values.POSTGRES_USER) { $values.POSTGRES_USER } else { 'postgres' }
    $database = if ($values.POSTGRES_DB) { $values.POSTGRES_DB } else { $user }
    return @{user=$user;database=$database}
}
