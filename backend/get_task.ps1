# Get task detail via API
$response = Invoke-WebRequest -Uri "http://localhost:8000/api/domain-factory/tasks/9475e881-d239-4bd6-ab1c-f5e7a553a790" -Headers @{
    "Authorization" = "Bearer test"
} -UseBasicParsing

$content = $response.Content | ConvertFrom-Json
$content | ConvertTo-Json -Depth 10
