<#
.SYNOPSIS
    Provision the Azure resources needed by the ACA-first robot demo.

.DESCRIPTION
    Creates the shared infrastructure for the customer demo:

      - Resource group
      - Microsoft Foundry resource for Voice Live and Foundry projects
      - Azure AI Search service for Foundry IQ
      - Azure Container Registry
      - Azure Container Apps environment
      - User-assigned managed identity

    Foundry Project, Foundry Hosted Agent, and Foundry IQ Knowledge Base are
    created or confirmed in Microsoft Foundry. After those exist, run
    deploy-container-app.ps1 with -ConfigureFoundryAgent to wire the agent to
    ACA /mcp and Foundry IQ.

.EXAMPLE
    az login
    .\scripts\provision-demo-resources.ps1 `
      -SubscriptionId "<subscription-id>" `
      -ResourceGroup "rg-avlb-demo" `
      -Location "eastus2" `
      -Prefix "avlbdemo" `
      -UpdateEnv
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,

    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [string]$Location = "eastus2",

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]{3,12}$')]
    [string]$Prefix,

    [string]$SearchServiceName = "",
    [string]$StorageAccountName = "",
    [string]$StorageContainerName = "kb-docs",
    [string]$AcrName = "",
    [string]$ContainerAppEnvironment = "",
    [string]$ManagedIdentityName = "",
    [string]$SearchSku = "basic",
    [string]$StorageSku = "Standard_LRS",
    [string]$FoundryProjectName = "",
    [string[]]$FallbackLocations = @(),
    [string[]]$SearchFallbackLocations = @(),

    [switch]$UpdateEnv,
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$az = (Get-Command az -ErrorAction SilentlyContinue).Source
if (-not $az) {
    $az = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
}
if (-not (Test-Path $az)) {
    throw "Azure CLI was not found. Install Azure CLI or add az to PATH before running this script."
}

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

function Get-AzJsonOrNull {
    param([string[]]$CommandArgs)

    $previousErrorActionPreference = $ErrorActionPreference
    $previousNativeErrorPreference = $PSNativeCommandUseErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        $PSNativeCommandUseErrorActionPreference = $false

        $output = & $az @CommandArgs 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $output) {
            return $null
        }
        return ($output | Out-String) | ConvertFrom-Json
    } catch {
        return $null
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $previousNativeErrorPreference
    }
}

function Add-RoleAssignment {
    param(
        [string]$PrincipalId,
        [string]$Role,
        [string]$Scope
    )

    $existing = & $az role assignment list `
        --assignee $PrincipalId `
        --scope $Scope `
        --query "[?roleDefinitionName=='$Role'].id | [0]" `
        --output tsv

    if (-not $existing) {
        Invoke-Az role assignment create `
            --assignee-object-id $PrincipalId `
            --assignee-principal-type ServicePrincipal `
            --role $Role `
            --scope $Scope `
            --output none
    }
}

function Set-EnvValue {
    param(
        [string[]]$Lines,
        [string]$Name,
        [string]$Value
    )

    $pattern = "^\s*$([regex]::Escape($Name))\s*="
    $newLine = "$Name=$Value"
    if ($Lines -match $pattern) {
        return $Lines -replace "$pattern.*", $newLine
    }
    return $Lines + $newLine
}

function Get-RegionalLocations {
    param(
        [string]$PrimaryLocation,
        [string[]]$FallbackLocations
    )

    $locations = New-Object System.Collections.Generic.List[string]
    $locations.Add($PrimaryLocation)

    if ($FallbackLocations.Count -gt 0) {
        foreach ($fallback in $FallbackLocations) {
            if ($fallback -and -not $locations.Contains($fallback)) {
                $locations.Add($fallback)
            }
        }
        return $locations.ToArray()
    }

    $nearby = switch ($PrimaryLocation.ToLowerInvariant()) {
        "eastus2" { @("eastus", "centralus") }
        "eastus" { @("eastus2", "centralus") }
        "centralus" { @("eastus2", "eastus") }
        "northcentralus" { @("centralus", "eastus2") }
        "southcentralus" { @("centralus", "eastus2") }
        "westus3" { @("westus2", "westus") }
        "westus2" { @("westus3", "westus") }
        "westus" { @("westus2", "westus3") }
        "westeurope" { @("northeurope", "uksouth") }
        "northeurope" { @("westeurope", "uksouth") }
        "southeastasia" { @("eastasia", "japaneast") }
        "eastasia" { @("southeastasia", "japaneast") }
        default { @("eastus", "centralus") }
    }

    foreach ($fallback in $nearby) {
        if ($fallback -and -not $locations.Contains($fallback)) {
            $locations.Add($fallback)
        }
    }
    return $locations.ToArray()
}

function New-RegionalResourceWithFallback {
    param(
        [string]$ResourceLabel,
        [string[]]$Locations,
        [scriptblock]$Create
    )

    $errors = @()
    foreach ($candidateLocation in $Locations) {
        Write-Host "    Trying $ResourceLabel location: $candidateLocation" -ForegroundColor DarkCyan
        try {
            $output = & $Create $candidateLocation
            return [pscustomobject]@{
                location = $candidateLocation
                output = $output
            }
        } catch {
            $errors += "${candidateLocation}: $($_.Exception.Message)"
            Write-Warning "$ResourceLabel could not be created in '$candidateLocation'. Trying next fallback if available."
        }
    }

    throw "$ResourceLabel could not be created in any configured location: $($Locations -join ', '). Last errors: $($errors -join ' | ')"
}

function Ensure-BlobContainer {
    param(
        [string]$AccountName,
        [string]$ContainerName
    )

    $accountKey = & $az storage account keys list `
        --resource-group $ResourceGroup `
        --account-name $AccountName `
        --query "[0].value" `
        --output tsv
    if ($LASTEXITCODE -ne 0 -or -not $accountKey) {
        throw "Could not retrieve a storage account key for '$AccountName' to create blob container '$ContainerName'."
    }

    Invoke-Az storage container create `
        --account-name $AccountName `
        --account-key $accountKey `
        --name $ContainerName `
        --public-access off `
        --output none
}

$FoundryResourceName = "$Prefix-foundry"
if (-not $SearchServiceName) { $SearchServiceName = "$Prefix-search" }
if (-not $StorageAccountName) { $StorageAccountName = ($Prefix -replace "[^a-z0-9]", "") + "st" }
if (-not $AcrName) { $AcrName = ($Prefix -replace "[^a-z0-9]", "") + "acr" }
if (-not $ContainerAppEnvironment) { $ContainerAppEnvironment = "$Prefix-aca-env" }
if (-not $ManagedIdentityName) { $ManagedIdentityName = "$Prefix-mi" }

$effectiveFallbackLocations = $FallbackLocations
if ($effectiveFallbackLocations.Count -eq 0 -and $SearchFallbackLocations.Count -gt 0) {
    $effectiveFallbackLocations = $SearchFallbackLocations
}
$regionalLocations = Get-RegionalLocations -PrimaryLocation $Location -FallbackLocations $effectiveFallbackLocations

Write-Host "==> Subscription: $SubscriptionId" -ForegroundColor Cyan
Invoke-Az account set --subscription $SubscriptionId

Write-Host "==> Resource group: $ResourceGroup ($Location)" -ForegroundColor Cyan
Invoke-Az group create --name $ResourceGroup --location $Location --output none

Write-Host "==> Microsoft Foundry resource: $FoundryResourceName" -ForegroundColor Cyan
if (-not (Test-AzCommand -CommandArgs @("cognitiveservices", "account", "show", "--name", $FoundryResourceName, "--resource-group", $ResourceGroup))) {
    $foundryCreate = New-RegionalResourceWithFallback `
        -ResourceLabel "Microsoft Foundry resource" `
        -Locations $regionalLocations `
        -Create {
            param([string]$CandidateLocation)

            Invoke-Az cognitiveservices account create `
                --name $FoundryResourceName `
                --resource-group $ResourceGroup `
                --location $CandidateLocation `
                --kind AIServices `
                --sku S0 `
                --custom-domain $FoundryResourceName `
                --allow-project-management true `
                --yes `
                --output none
        }
    $foundryLocation = $foundryCreate.location
} else {
    $foundryLocation = (& $az cognitiveservices account show --name $FoundryResourceName --resource-group $ResourceGroup --query "location" -o tsv)
    if (-not $foundryLocation) {
        $foundryLocation = $Location
    }
}
$foundryEndpoint = (& $az cognitiveservices account show --name $FoundryResourceName --resource-group $ResourceGroup --query "properties.endpoint" -o tsv)

Write-Host "==> Azure AI Search: $SearchServiceName ($SearchSku)" -ForegroundColor Cyan
if (-not (Test-AzCommand -CommandArgs @("search", "service", "show", "--name", $SearchServiceName, "--resource-group", $ResourceGroup))) {
    $searchCreate = New-RegionalResourceWithFallback `
        -ResourceLabel "Azure AI Search" `
        -Locations $regionalLocations `
        -Create {
            param([string]$CandidateLocation)

            Invoke-Az search service create `
                --name $SearchServiceName `
                --resource-group $ResourceGroup `
                --location $CandidateLocation `
                --sku $SearchSku `
                --output none
        }
    $searchLocation = $searchCreate.location
} else {
    $searchLocation = (& $az search service show --name $SearchServiceName --resource-group $ResourceGroup --query "location" -o tsv)
    if (-not $searchLocation) {
        $searchLocation = $Location
    }
}
$searchEndpoint = "https://$SearchServiceName.search.windows.net"

Write-Host "==> Azure Storage Account: $StorageAccountName ($StorageSku)" -ForegroundColor Cyan
if (-not (Test-AzCommand -CommandArgs @("storage", "account", "show", "--name", $StorageAccountName, "--resource-group", $ResourceGroup))) {
    $storageCreate = New-RegionalResourceWithFallback `
        -ResourceLabel "Azure Storage Account" `
        -Locations $regionalLocations `
        -Create {
            param([string]$CandidateLocation)

            Invoke-Az storage account create `
                --name $StorageAccountName `
                --resource-group $ResourceGroup `
                --location $CandidateLocation `
                --sku $StorageSku `
                --kind StorageV2 `
                --https-only true `
                --allow-blob-public-access false `
                --output none
        }
    $storageLocation = $storageCreate.location
} else {
    $storageLocation = (& $az storage account show --name $StorageAccountName --resource-group $ResourceGroup --query "location" -o tsv)
    if (-not $storageLocation) {
        $storageLocation = $Location
    }
}
$storageBlobEndpoint = (& $az storage account show --name $StorageAccountName --resource-group $ResourceGroup --query "primaryEndpoints.blob" -o tsv)
if (-not $storageBlobEndpoint) {
    $storageBlobEndpoint = "https://$StorageAccountName.blob.core.windows.net/"
}

Write-Host "==> Blob container: $StorageContainerName" -ForegroundColor Cyan
Ensure-BlobContainer -AccountName $StorageAccountName -ContainerName $StorageContainerName

Write-Host "==> Azure Container Registry: $AcrName" -ForegroundColor Cyan
if (-not (Test-AzCommand -CommandArgs @("acr", "show", "--name", $AcrName, "--resource-group", $ResourceGroup))) {
    $acrCreate = New-RegionalResourceWithFallback `
        -ResourceLabel "Azure Container Registry" `
        -Locations $regionalLocations `
        -Create {
            param([string]$CandidateLocation)

            Invoke-Az acr create `
                --name $AcrName `
                --resource-group $ResourceGroup `
                --location $CandidateLocation `
                --sku Basic `
                --admin-enabled false `
                --output none
        }
    $acrLocation = $acrCreate.location
} else {
    $acrLocation = (& $az acr show --name $AcrName --resource-group $ResourceGroup --query "location" -o tsv)
    if (-not $acrLocation) {
        $acrLocation = $Location
    }
}
$acrId = (& $az acr show --name $AcrName --resource-group $ResourceGroup --query "id" -o tsv)

Write-Host "==> Azure Container Apps Environment: $ContainerAppEnvironment" -ForegroundColor Cyan
if (-not (Test-AzCommand -CommandArgs @("containerapp", "env", "show", "--name", $ContainerAppEnvironment, "--resource-group", $ResourceGroup))) {
    $acaEnvCreate = New-RegionalResourceWithFallback `
        -ResourceLabel "Azure Container Apps Environment" `
        -Locations $regionalLocations `
        -Create {
            param([string]$CandidateLocation)

            Invoke-Az containerapp env create `
                --name $ContainerAppEnvironment `
                --resource-group $ResourceGroup `
                --location $CandidateLocation `
                --output none
        }
    $acaEnvLocation = $acaEnvCreate.location
} else {
    $acaEnvLocation = (& $az containerapp env show --name $ContainerAppEnvironment --resource-group $ResourceGroup --query "location" -o tsv)
    if (-not $acaEnvLocation) {
        $acaEnvLocation = $Location
    }
}

Write-Host "==> Managed Identity: $ManagedIdentityName" -ForegroundColor Cyan
$identity = Get-AzJsonOrNull -CommandArgs @("identity", "show", "--resource-group", $ResourceGroup, "--name", $ManagedIdentityName, "--output", "json")
if (-not $identity) {
    $identityCreate = New-RegionalResourceWithFallback `
        -ResourceLabel "Managed Identity" `
        -Locations $regionalLocations `
        -Create {
            param([string]$CandidateLocation)

            Invoke-Az identity create `
                --resource-group $ResourceGroup `
                --name $ManagedIdentityName `
                --location $CandidateLocation `
                --output json
        }
    $identity = ($identityCreate.output | Out-String) | ConvertFrom-Json
    $managedIdentityLocation = $identityCreate.location
} else {
    $managedIdentityLocation = $identity.location
    if (-not $managedIdentityLocation) {
        $managedIdentityLocation = $Location
    }
}

$principalId = $identity.principalId
$clientId = $identity.clientId
$identityId = $identity.id

$base = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers"
$foundryScope = "$base/Microsoft.CognitiveServices/accounts/$FoundryResourceName"
$searchScope = "$base/Microsoft.Search/searchServices/$SearchServiceName"
$storageScope = "$base/Microsoft.Storage/storageAccounts/$StorageAccountName"

Write-Host "==> RBAC for managed identity" -ForegroundColor Cyan
Add-RoleAssignment -PrincipalId $principalId -Role "AcrPull" -Scope $acrId
Add-RoleAssignment -PrincipalId $principalId -Role "Cognitive Services User" -Scope $foundryScope
Add-RoleAssignment -PrincipalId $principalId -Role "Cognitive Services OpenAI User" -Scope $foundryScope
Add-RoleAssignment -PrincipalId $principalId -Role "Search Service Contributor" -Scope $searchScope
Add-RoleAssignment -PrincipalId $principalId -Role "Search Index Data Contributor" -Scope $searchScope
Add-RoleAssignment -PrincipalId $principalId -Role "Search Index Data Reader" -Scope $searchScope
Add-RoleAssignment -PrincipalId $principalId -Role "Storage Blob Data Contributor" -Scope $storageScope

$foundryProjectResourceId = ""
if ($FoundryProjectName) {
    $foundryProjectResourceId = "$foundryScope/projects/$FoundryProjectName"
    Add-RoleAssignment -PrincipalId $principalId -Role "Azure AI Developer" -Scope $foundryProjectResourceId
}

$resolved = [ordered]@{
    AZURE_RESOURCE_GROUP                  = $ResourceGroup
    AZURE_TENANT_ID                       = (& $az account show --query "tenantId" -o tsv)
    AZURE_CLIENT_ID                       = $clientId
    FOUNDRY_RESOURCE_NAME                 = $FoundryResourceName
    FOUNDRY_REGION                        = $foundryLocation
    VOICE_LIVE_ENDPOINT                   = $foundryEndpoint
    AZURE_AI_SEARCH_SERVICE_NAME          = $SearchServiceName
    AZURE_AI_SEARCH_LOCATION              = $searchLocation
    FOUNDRY_IQ_SEARCH_ENDPOINT            = $searchEndpoint
    AZURE_STORAGE_ACCOUNT_NAME            = $StorageAccountName
    AZURE_STORAGE_BLOB_SERVICE_URL        = $storageBlobEndpoint.TrimEnd("/")
    AZURE_STORAGE_CONTAINER_NAME          = $StorageContainerName
    AZURE_STORAGE_LOCATION                = $storageLocation
    AZURE_CONTAINER_APPS_ENVIRONMENT_NAME = $ContainerAppEnvironment
    AZURE_CONTAINER_APPS_LOCATION         = $acaEnvLocation
    AZURE_CONTAINER_REGISTRY_LOCATION     = $acrLocation
    AZURE_MANAGED_IDENTITY_LOCATION       = $managedIdentityLocation
}
if ($FoundryProjectName) {
    $resolved.FOUNDRY_PROJECT_NAME = $FoundryProjectName
    $resolved.FOUNDRY_PROJECT_RESOURCE_ID = $foundryProjectResourceId
}

Write-Host ""
Write-Host "==================== Provisioned demo resources ====================" -ForegroundColor Green
foreach ($item in $resolved.GetEnumerator()) {
    Write-Host ("  {0,-38} {1}" -f $item.Key, $item.Value)
}
Write-Host ("  {0,-38} {1}" -f "ACR_NAME", $AcrName)
Write-Host ("  {0,-38} {1}" -f "STORAGE_ACCOUNT_NAME", $StorageAccountName)
Write-Host ("  {0,-38} {1}" -f "STORAGE_CONTAINER_NAME", $StorageContainerName)
Write-Host ("  {0,-38} {1}" -f "MANAGED_IDENTITY_RESOURCE_ID", $identityId)
Write-Host ("  {0,-38} {1}" -f "MANAGED_IDENTITY_CLIENT_ID", $clientId)
Write-Host "====================================================================" -ForegroundColor Green

if ($UpdateEnv) {
    $envPath = Join-Path $ProjectRoot $EnvFile
    if (-not (Test-Path $envPath)) {
        Copy-Item (Join-Path $ProjectRoot ".env.example") $envPath
    }
    $lines = Get-Content $envPath
    foreach ($item in $resolved.GetEnumerator()) {
        $lines = Set-EnvValue -Lines $lines -Name $item.Key -Value $item.Value
    }
    Set-Content -Path $envPath -Value $lines -Encoding UTF8
    Write-Host "==> Wrote resolved values into $EnvFile" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Upload knowledge files into blob container '$StorageContainerName' in storage account '$StorageAccountName'."
Write-Host "  2. In Microsoft Foundry, create the Foundry Project under '$FoundryResourceName'."
Write-Host "  3. Create a Foundry IQ Blob knowledge source backed by '$StorageAccountName/$StorageContainerName', then create the Knowledge Base."
Write-Host "  4. Create the Foundry Hosted Agent and copy the project endpoint, agent name/version, and knowledge base name into .env."
Write-Host "  5. Deploy the app:"
Write-Host "     .\scripts\deploy-container-app.ps1 -AcrName $AcrName -ContainerAppEnvironment $ContainerAppEnvironment \"
Write-Host "       -ManagedIdentityResourceId `"$identityId`" -ManagedIdentityClientId `"$clientId`" -ConfigureFoundryAgent ..."

[pscustomobject]@{
    resourceGroup = $ResourceGroup
    foundryResourceName = $FoundryResourceName
    foundryLocation = $foundryLocation
    voiceLiveEndpoint = $foundryEndpoint
    searchServiceName = $SearchServiceName
    searchLocation = $searchLocation
    foundryIqSearchEndpoint = $searchEndpoint
    storageAccountName = $StorageAccountName
    storageLocation = $storageLocation
    storageBlobServiceUrl = $storageBlobEndpoint.TrimEnd("/")
    storageContainerName = $StorageContainerName
    acrName = $AcrName
    acrLocation = $acrLocation
    containerAppEnvironment = $ContainerAppEnvironment
    containerAppEnvironmentLocation = $acaEnvLocation
    managedIdentityName = $ManagedIdentityName
    managedIdentityLocation = $managedIdentityLocation
    managedIdentityResourceId = $identityId
    managedIdentityClientId = $clientId
    foundryProjectResourceId = $foundryProjectResourceId
}
