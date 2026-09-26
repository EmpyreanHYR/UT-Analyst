$ErrorActionPreference = "Stop"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "UT-Analyst" `
    --collect-all pyqtgraph `
    main.py

Write-Host "Package created at dist/UT-Analyst"
