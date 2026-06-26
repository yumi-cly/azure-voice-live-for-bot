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

    [string]$FoundryResourceName = "",
    [string]$SearchServiceName = "",
    [string]$AcrName = "",
    [string]$ContainerAppEnvironment = "",
    [string]$ManagedIdentityName = "",
    [string]$SearchSku = "basic",
    [string]$FoundryProjectName = "",

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

if (-not $FoundryResourceName) { $FoundryResourceName = "$Prefix-foundry" }
if (-not $SearchServiceName) { $SearchServiceName = "$Prefix-search" }
if (-not $AcrName) { $AcrName = ($Prefix -replace "[^a-z0-9]", "") + "acr" }
if (-not $ContainerAppEnvironment) { $ContainerAppEnvironment = "$Prefix-aca-env" }
if (-not $ManagedIdentityName) { $ManagedIdentityName = "$Prefix-mi" }

Write-Host "==> Subscription: $SubscriptionId" -ForegroundColor Cyan
Invoke-Az account set --subscription $SubscriptionId

Write-Host "==> Resource group: $ResourceGroup ($Location)" -ForegroundColor Cyan
Invoke-Az group create --name $ResourceGroup --location $Location --output none

Write-Host "==> Microsoft Foundry resource: $FoundryResourceName" -ForegroundColor Cyan
$existingFoundry = & $az cognitiveservices account show --name $FoundryResourceName --resource-group $ResourceGroup --output json 2>$null
if (-not $existingFoundry) {
    Invoke-Az cognitiveservices account create `
        --name $FoundryResourceName `
        --resource-group $ResourceGroup `
        --location $Location `
        --kind AIServices `
        --sku S0 `
        --custom-domain $FoundryResourceName `
        --allow-project-management true `
        --yes `
        --output none
}
$foundryEndpoint = (& $az cognitiveservices account show --name $FoundryResourceName --resource-group $ResourceGroup --query "properties.endpoint" -o tsv)

Write-Host "==> Azure AI Search: $SearchServiceName ($SearchSku)" -ForegroundColor Cyan
$existingSearch = & $az search service show --name $SearchServiceName --resource-group $ResourceGroup --output json 2>$null
if (-not $existingSearch) {
    Invoke-Az search service create `
        --name $SearchServiceName `
        --resource-group $ResourceGroup `
        --location $Location `
        --sku $SearchSku `
        --output none
}
$searchEndpoint = "https://$SearchServiceName.search.windows.net"

Write-Host "==> Azure Container Registry: $AcrName" -ForegroundColor Cyan
$existingAcr = & $az acr show --name $AcrName --resource-group $ResourceGroup --output json 2>$null
if (-not $existingAcr) {
    Invoke-Az acr create `
        --name $AcrName `
        --resource-group $ResourceGroup `
        --location $Location `
        --sku Basic `
        --admin-enabled false `
        --output none
}
$acrId = (& $az acr show --name $AcrName --resource-group $ResourceGroup --query "id" -o tsv)

Write-Host "==> Azure Container Apps Environment: $ContainerAppEnvironment" -ForegroundColor Cyan
$existingAcaEnv = & $az containerapp env show --name $ContainerAppEnvironment --resource-group $ResourceGroup --output json 2>$null
if (-not $existingAcaEnv) {
    Invoke-Az containerapp env create `
        --name $ContainerAppEnvironment `
        --resource-group $ResourceGroup `
        --location $Location `
        --output none
}

Write-Host "==> Managed Identity: $ManagedIdentityName" -ForegroundColor Cyan
$identity = & $az identity show --resource-group $ResourceGroup --name $ManagedIdentityName --output json 2>$null | ConvertFrom-Json
if (-not $identity) {
    $identity = Invoke-Az identity create `
        --resource-group $ResourceGroup `
        --name $ManagedIdentityName `
        --location $Location `
        --output json | ConvertFrom-Json
}

$principalId = $identity.principalId
$clientId = $identity.clientId
$identityId = $identity.id

$base = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers"
$foundryScope = "$base/Microsoft.CognitiveServices/accounts/$FoundryResourceName"
$searchScope = "$base/Microsoft.Search/searchServices/$SearchServiceName"

Write-Host "==> RBAC for managed identity" -ForegroundColor Cyan
Add-RoleAssignment -PrincipalId $principalId -Role "AcrPull" -Scope $acrId
Add-RoleAssignment -PrincipalId $principalId -Role "Cognitive Services User" -Scope $foundryScope
Add-RoleAssignment -PrincipalId $principalId -Role "Cognitive Services OpenAI User" -Scope $foundryScope
Add-RoleAssignment -PrincipalId $principalId -Role "Search Service Contributor" -Scope $searchScope
Add-RoleAssignment -PrincipalId $principalId -Role "Search Index Data Contributor" -Scope $searchScope
Add-RoleAssignment -PrincipalId $principalId -Role "Search Index Data Reader" -Scope $searchScope

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
    FOUNDRY_REGION                        = $Location
    AZURE_AI_SEARCH_SERVICE_NAME          = $SearchServiceName
    AZURE_CONTAINER_APPS_ENVIRONMENT_NAME = $ContainerAppEnvironment
    VOICE_LIVE_ENDPOINT                   = $foundryEndpoint
    FOUNDRY_IQ_SEARCH_ENDPOINT            = $searchEndpoint
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
Write-Host "  1. In Microsoft Foundry, create/open the Foundry Project under '$FoundryResourceName'."
Write-Host "  2. Create or connect a Foundry IQ Knowledge Base backed by '$SearchServiceName'."
Write-Host "  3. Create a Foundry Hosted Agent and copy the agent name/version into .env."
Write-Host "  4. Deploy the app:"
Write-Host "     .\scripts\deploy-container-app.ps1 -AcrName $AcrName -ContainerAppEnvironment $ContainerAppEnvironment \"
Write-Host "       -ManagedIdentityResourceId `"$identityId`" -ManagedIdentityClientId `"$clientId`" -ConfigureFoundryAgent ..."

[pscustomobject]@{
    resourceGroup = $ResourceGroup
    foundryResourceName = $FoundryResourceName
    voiceLiveEndpoint = $foundryEndpoint
    searchServiceName = $SearchServiceName
    foundryIqSearchEndpoint = $searchEndpoint
    acrName = $AcrName
    containerAppEnvironment = $ContainerAppEnvironment
    managedIdentityName = $ManagedIdentityName
    managedIdentityResourceId = $identityId
    managedIdentityClientId = $clientId
    foundryProjectResourceId = $foundryProjectResourceId
}
