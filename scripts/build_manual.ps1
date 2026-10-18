# 编译用户说明书 PDF（Direction/main.pdf）。
#
# 用法：
#   scripts\build_manual.ps1
#
# 说明：说明书入口为 Direction/main.tex，使用 ctex 宏包，需用 XeLaTeX 编译；
# 交叉引用与目录需要连续编译两遍。

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$manualDir = Join-Path $projectRoot "Direction"
Set-Location $manualDir

if (-not (Get-Command xelatex -ErrorAction SilentlyContinue)) {
    throw "未找到 xelatex，请先安装 TeX Live 或 MiKTeX。"
}

xelatex -interaction=nonstopmode main.tex
xelatex -interaction=nonstopmode main.tex

Write-Host "说明书已生成: Direction/main.pdf"
