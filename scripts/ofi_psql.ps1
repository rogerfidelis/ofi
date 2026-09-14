param(
    [string]$File
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot ".env"

if (-not (Test-Path $EnvFile)) {
    Write-Error ".env não encontrado em $EnvFile"
    exit 1
}

# ------------------------------------------------------------
# CARREGA VARIÁVEIS DO .env
# ------------------------------------------------------------

Get-Content $EnvFile | ForEach-Object {

    $linha = $_.Trim()

    if (
        $linha -and
        -not $linha.StartsWith("#") -and
        $linha.Contains("=")
    ) {

        $nome, $valor = $linha -split "=", 2

        $nome = $nome.Trim()
        $valor = $valor.Trim()

        # Remove aspas simples ou duplas
        $valor = $valor.Trim('"').Trim("'")

        Set-Item -Path "Env:$nome" -Value $valor
    }
}


# ------------------------------------------------------------
# VARIÁVEIS PADRÃO DO POSTGRESQL
# ------------------------------------------------------------

$env:PGHOST     = $env:OFI_DB_HOST
$env:PGPORT     = $env:OFI_DB_PORT
$env:PGDATABASE = $env:OFI_DB_NAME
$env:PGUSER     = $env:OFI_DB_USER
$env:PGPASSWORD = $env:OFI_DB_PASSWORD


# ------------------------------------------------------------
# VALIDAÇÃO
# ------------------------------------------------------------

$obrigatorias = @(
    "PGHOST",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD"
)

foreach ($variavel in $obrigatorias) {

    if (-not (Get-Item "Env:$variavel" -ErrorAction SilentlyContinue).Value) {

        Write-Error "Variável $variavel não definida."
        exit 1
    }
}


# ------------------------------------------------------------
# EXECUTA PSQL
# ------------------------------------------------------------

if ($File) {

    & psql `
        -v ON_ERROR_STOP=1 `
        -f $File

}
else {

    & psql
}


$codigo = $LASTEXITCODE


# ------------------------------------------------------------
# REMOVE SENHA DA SESSÃO DO SCRIPT
# ------------------------------------------------------------

Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

exit $codigo