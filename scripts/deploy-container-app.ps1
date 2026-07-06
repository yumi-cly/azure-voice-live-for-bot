param(
    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,

    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$Location,

    [Parameter(Mandatory = $true)]
    [string]$AcrName,

    [Parameter(Mandatory = $true)]
    [string]$ContainerAppEnvironment,

    [Parameter(Mandatory = $true)]
    [string]$ContainerAppName,

    [string]$ManagedIdentityResourceId = "",
    [string]$ManagedIdentityClientId = "",
    [string]$EnvFile = ".env",
    [string]$ImageTag = "manual",
    [switch]$SkipEnvFromFile,
    [switch]$ConfigureFoundryAgent,
    [string]$AgentModel = "",
    [string]$BaseAgentVersion = ""
)

$ErrorActionPreference = "Stop"

$az = (Get-Command az -ErrorAction SilentlyContinue).Source
if (-not $az) {
    $az = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
}
if (-not (Test-Path $az)) {
    throw "Azure CLI was not found. Install Azure CLI before running this script."
}
if (-not $ManagedIdentityResourceId -or -not $ManagedIdentityClientId) {
    throw "ACA-first deployment requires -ManagedIdentityResourceId and -ManagedIdentityClientId so the app can pull from ACR and use Entra auth for Voice Live."
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Invoke-Az {
    & $az @args
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($args -join ' ')"
    }
}

function Test-AzCommand {
    param([string[]]$CommandArgs)

    $previousErrorActionPreference = $ErrorActionPreference
    $previousNativeErrorPreference = $PSNativeCommandUseErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        $PSNativeCommandUseErrorActionPreference = $false

        & $az @CommandArgs 1>$null 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $previousNativeErrorPreference
    }
}

function Read-EnvFile {
    param([string]$Path)

    $values = [ordered]@{}
    if (-not (Test-Path $Path)) {
        return $values
    }

    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $name, $value = $trimmed.Split("=", 2)
        $name = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($name -and $value) {
            $values[$name] = $value
        }
    }
    return $values
}

function Convert-ToSecretName {
    param([string]$Name)
    $secret = $Name.ToLowerInvariant() -replace "_", "-"
    $secret = $secret -replace "[^a-z0-9-]", "-"
    $secret = $secret.Trim("-")
    if ($secret.Length -gt 60) {
        $secret = $secret.Substring(0, 60).Trim("-")
    }
    return $secret
}

function Is-SecretEnvName {
    param([string]$Name)
    return $Name -match "(KEY|SECRET|TOKEN|PASSWORD)$" -or $Name -match "API_KEY$"
}

function Resolve-Python {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($python) {
        Write-Host "==> Creating local Python virtual environment: .venv" -ForegroundColor Cyan
        & $python -m venv (Join-Path $ProjectRoot ".venv")
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
            throw "Failed to create .venv. Create it manually or add a working Python to PATH before using -ConfigureFoundryAgent."
        }
        return $venvPython
    }
    throw "Python was not found. Create .venv or add python to PATH before using -ConfigureFoundryAgent."
}

function Ensure-FoundryConfigureDependencies {
    param([string]$Python)

    $checkScript = "import azure.ai.projects; import azure.identity; import dotenv; import pydantic_settings"
    & $Python -c $checkScript 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Write-Host "==> Installing local Python dependencies for Foundry Agent configuration" -ForegroundColor Cyan
    & $Python -m pip install --disable-pip-version-check --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip in local Python environment."
    }

    & $Python -m pip install --disable-pip-version-check `
        python-dotenv `
        pydantic-settings `
        azure-identity `
        azure-ai-projects
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install Python dependencies for Foundry Agent configuration."
    }

    & $Python -c $checkScript 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependencies for Foundry Agent configuration are still missing after installation."
    }
}

Invoke-Az account set --subscription $SubscriptionId

$groupExists = Invoke-Az group exists --name $ResourceGroup --output tsv
if ($groupExists -ne "true") {
    Invoke-Az group create --name $ResourceGroup --location $Location --output none
}

$acrExists = Test-AzCommand -CommandArgs @("acr", "show", "--name", $AcrName, "--resource-group", $ResourceGroup)
if (-not $acrExists) {
    Invoke-Az acr create --name $AcrName --resource-group $ResourceGroup --location $Location --sku Basic --admin-enabled false --output none
}

$acaEnvExists = Test-AzCommand -CommandArgs @("containerapp", "env", "show", "--name", $ContainerAppEnvironment, "--resource-group", $ResourceGroup)
if (-not $acaEnvExists) {
    Invoke-Az containerapp env create `
        --name $ContainerAppEnvironment `
        --resource-group $ResourceGroup `
        --location $Location `
        --output none
}

$acrId = Invoke-Az acr show --name $AcrName --resource-group $ResourceGroup --query "id" --output tsv

if ($ManagedIdentityResourceId) {
    $principalId = Invoke-Az identity show --ids $ManagedIdentityResourceId --query "principalId" --output tsv
    $existingAcrPull = Invoke-Az role assignment list `
        --assignee $principalId `
        --scope $acrId `
        --query "[?roleDefinitionName=='AcrPull'].id | [0]" `
        --output tsv
    if (-not $existingAcrPull) {
        Invoke-Az role assignment create `
            --assignee-object-id $principalId `
            --assignee-principal-type ServicePrincipal `
            --role "AcrPull" `
            --scope $acrId `
            --output none
    }
}

$image = "$AcrName.azurecr.io/azure-voice-live-for-bot:$ImageTag"
Invoke-Az acr build --registry $AcrName --image "azure-voice-live-for-bot:$ImageTag" . --output none

$envValues = @("PORT=8000")
$secretValues = @()
$fileValues = [ordered]@{}
if (-not $SkipEnvFromFile) {
    $resolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $ProjectRoot $EnvFile }
    $fileValues = Read-EnvFile -Path $resolvedEnvFile
    foreach ($key in $fileValues.Keys) {
        if ($key -in @("PORT")) {
            continue
        }
        if (Is-SecretEnvName -Name $key) {
            $secretName = Convert-ToSecretName -Name $key
            $secretValues += "$secretName=$($fileValues[$key])"
            $envValues += "$key=secretref:$secretName"
        } else {
            $envValues += "$key=$($fileValues[$key])"
        }
    }
}

$envValues = $envValues | Where-Object { $_ -notmatch "^WEB_ALLOWED_ORIGINS=" }
$envValues += "WEB_ALLOWED_ORIGINS=*"
if ($ManagedIdentityClientId) {
    $envValues = $envValues | Where-Object { $_ -notmatch "^AZURE_CLIENT_ID=" }
    $envValues += "AZURE_CLIENT_ID=$ManagedIdentityClientId"
}

$appExists = Test-AzCommand -CommandArgs @("containerapp", "show", "--name", $ContainerAppName, "--resource-group", $ResourceGroup)
if (-not $appExists) {
    $createArgs = @(
        "containerapp", "create",
        "--name", $ContainerAppName,
        "--resource-group", $ResourceGroup,
        "--environment", $ContainerAppEnvironment,
        "--image", $image,
        "--target-port", "8000",
        "--ingress", "external",
        "--registry-server", "$AcrName.azurecr.io",
        "--output", "none"
    )
    if ($ManagedIdentityResourceId) {
        $createArgs += @("--user-assigned", $ManagedIdentityResourceId, "--registry-identity", $ManagedIdentityResourceId)
    }
    Invoke-Az @createArgs
} else {
    if ($ManagedIdentityResourceId) {
        Invoke-Az containerapp identity assign `
            --name $ContainerAppName `
            --resource-group $ResourceGroup `
            --user-assigned $ManagedIdentityResourceId `
            --output none
    }
    Invoke-Az containerapp update `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --image $image `
        --output none
}

if ($secretValues.Count -gt 0) {
    Invoke-Az containerapp secret set `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --secrets @secretValues `
        --output none
}

Invoke-Az containerapp update `
    --name $ContainerAppName `
    --resource-group $ResourceGroup `
    --set-env-vars @envValues `
    --output none

$fqdn = Invoke-Az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" --output tsv
$appUrl = "https://$fqdn"
$mcpUrl = "$appUrl/mcp"
$configuredAgentVersion = ""

Invoke-Az containerapp update `
    --name $ContainerAppName `
    --resource-group $ResourceGroup `
    --set-env-vars "MCP_SERVER_URL=$mcpUrl" `
    --output none

if ($ConfigureFoundryAgent) {
    $python = Resolve-Python
    Ensure-FoundryConfigureDependencies -Python $python
    if (-not $AgentModel -and $fileValues.Contains("FOUNDRY_MODEL_NAME")) {
        $AgentModel = $fileValues["FOUNDRY_MODEL_NAME"]
    }
    if (-not $AgentModel) {
        throw "-AgentModel or FOUNDRY_MODEL_NAME is required when -ConfigureFoundryAgent is used. Use the actual Foundry model deployment name."
    }
    $configureArgs = @(
        "scripts\configure_foundry_mcp_agent.py",
        "--mcp-url", $mcpUrl,
        "--model", $AgentModel,
        "--update-env"
    )
    if ($BaseAgentVersion) {
        $configureArgs += @("--base-version", $BaseAgentVersion)
    }

    $configureOutput = & $python @configureArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Foundry Agent configuration failed."
    }
    $configureText = ($configureOutput | Out-String).Trim()
    $configureResult = $configureText | ConvertFrom-Json
    $configuredAgentVersion = [string]$configureResult.agent_version

    if (-not $configuredAgentVersion) {
        throw "Foundry Agent configuration did not return an agent version."
    }

    Invoke-Az containerapp update `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --set-env-vars "MCP_SERVER_URL=$mcpUrl" "FOUNDRY_AGENT_VERSION=$configuredAgentVersion" `
        --output none
}

[pscustomobject]@{
    containerAppName = $ContainerAppName
    image = $image
    url = $appUrl
    mcpUrl = $mcpUrl
    foundryAgentVersion = $configuredAgentVersion
    envFromFile = -not $SkipEnvFromFile
}
