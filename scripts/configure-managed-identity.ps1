param(
    [string]$SubscriptionId = "",
    [string]$ResourceGroup = "",
    [string]$Location = "eastus2",
    [string]$IdentityName = "mi-avlb-broker-dev-eus2",
    [string]$FoundryResourceName = "",
    [string]$FoundryProjectName = "",
    [string]$SearchServiceName = "",
    [string]$StorageAccountName = "",
    [string]$ContainerAppName = ""
)

$ErrorActionPreference = "Stop"

$requiredValues = @{
    SubscriptionId = $SubscriptionId
    ResourceGroup = $ResourceGroup
    FoundryResourceName = $FoundryResourceName
    FoundryProjectName = $FoundryProjectName
    SearchServiceName = $SearchServiceName
}
foreach ($item in $requiredValues.GetEnumerator()) {
    if (-not $item.Value) {
        throw "Missing required parameter: $($item.Key)"
    }
}

$script:AzPath = (Get-Command az -ErrorAction SilentlyContinue).Source
if (-not $script:AzPath) {
    $script:AzPath = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
}
if (-not (Test-Path $script:AzPath)) {
    throw "Azure CLI was not found. Install Azure CLI or add az to PATH before running this script."
}
function Invoke-AzCli {
    & $script:AzPath @args
}
Set-Alias -Name az -Value Invoke-AzCli -Scope Script

az account set --subscription $SubscriptionId

$identity = az identity show `
    --resource-group $ResourceGroup `
    --name $IdentityName `
    --output json 2>$null | ConvertFrom-Json

if (-not $identity) {
    $identity = az identity create `
        --resource-group $ResourceGroup `
        --name $IdentityName `
        --location $Location `
        --output json | ConvertFrom-Json
}

$principalId = $identity.principalId
$clientId = $identity.clientId
$identityId = $identity.id

function Add-RoleAssignment {
    param(
        [string]$Role,
        [string]$Scope
    )

    $existing = az role assignment list `
        --assignee $principalId `
        --scope $Scope `
        --query "[?roleDefinitionName=='$Role'].id | [0]" `
        --output tsv

    if (-not $existing) {
        az role assignment create `
            --assignee-object-id $principalId `
            --assignee-principal-type ServicePrincipal `
            --role $Role `
            --scope $Scope `
            --output none
    }
}

$base = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers"
$foundryScope = "$base/Microsoft.CognitiveServices/accounts/$FoundryResourceName"
$foundryProjectScope = "$foundryScope/projects/$FoundryProjectName"
$searchScope = "$base/Microsoft.Search/searchServices/$SearchServiceName"

Add-RoleAssignment -Role "Azure AI Developer" -Scope $foundryProjectScope
Add-RoleAssignment -Role "Cognitive Services User" -Scope $foundryScope
Add-RoleAssignment -Role "Cognitive Services OpenAI User" -Scope $foundryScope
Add-RoleAssignment -Role "Search Service Contributor" -Scope $searchScope
Add-RoleAssignment -Role "Search Index Data Contributor" -Scope $searchScope
Add-RoleAssignment -Role "Search Index Data Reader" -Scope $searchScope

if ($StorageAccountName) {
    $storageScope = "$base/Microsoft.Storage/storageAccounts/$StorageAccountName"
    Add-RoleAssignment -Role "Storage Blob Data Contributor" -Scope $storageScope
}

if ($ContainerAppName) {
    az containerapp identity assign `
        --resource-group $ResourceGroup `
        --name $ContainerAppName `
        --user-assigned $identityId `
        --output none

    az containerapp update `
        --resource-group $ResourceGroup `
        --name $ContainerAppName `
        --set-env-vars "AZURE_CLIENT_ID=$clientId" `
        --output none
}

[pscustomobject]@{
    identityName = $IdentityName
    clientId = $clientId
    principalId = $principalId
    identityId = $identityId
    containerAppAttached = [bool]$ContainerAppName
}
