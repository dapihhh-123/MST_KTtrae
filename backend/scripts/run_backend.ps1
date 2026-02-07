# Check if venv exists, if so activate it
if (Test-Path "venv") {
    Write-Host "Activating venv..."
    .\venv\Scripts\Activate.ps1
}

# Set PYTHONPATH to include current directory so imports work
$env:PYTHONPATH = "$PWD"

Write-Host "Starting Backend..."
# Run uvicorn with reload for development
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001
